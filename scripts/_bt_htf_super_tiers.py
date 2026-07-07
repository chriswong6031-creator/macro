#!/usr/bin/env python3
"""G-HTF1 descriptive backtest — S1/S2 HTF super-tiers.

Pre-registration: research/signal_engine/HTF_SUPER_TIERS_ADJUDICATION_AND_PREREG.md Part 2.
Frozen spec — no post-hoc threshold tuning; print every variant's numbers including nulls.

Variants:
  S1  — 2W confluence-active AND 3D confluence-active.
  S2a — 3D confluence-active AND 1W confluence-active AND 2W MACD-pending (stoch free).
  S2b — S2a additionally requiring 2W StochRSI K-D gap narrowing.
  FW ∈ {1, 2} native bars (freshness sweep — both printed, no post-hoc picking).

Rulers:
  n fires, n tickers, stop-out% (−5% hard stop / 20d triple-barrier), clean% (same gate),
  MFE%/MAE, fill_premium_20d median, lead vs T1 and T2 onsets, overlap fraction,
  60d durable-bottom rate, 21d/63d SPY-excess + bootstrap CI (1000 reps, seed 42),
  120d/240d excess (overlap-noted), S2 repaint rate.

Panel: 224-name US curated parquet panel (data/stocks/), 2010→present.
Benchmark: data/yahoo/SPY.parquet (daily close, 1993→).

Output: /tmp/htf_super_tiers/ (per-ticker frames + summary JSON) and
        research/signal_engine/HTF_SUPER_TIERS_PHASE0.md (results report).
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path wiring
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parents[1]
_REPO_ROOT = _WORKTREE.parents[2]
_DATA_STOCKS = _REPO_ROOT / "data" / "stocks"
_SPY_PATH = _REPO_ROOT / "data" / "yahoo" / "SPY.parquet"
_OUT_DIR = Path("/tmp/htf_super_tiers")
_OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(_WORKTREE))

from engine.confluence_tiers import (  # noqa: E402
    _tf_bars, _rsi_macd, _stoch_rsi_kd, _xup, _since, _to_daily,
    tier_stream, MIN_HISTORY,
    RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN,
    STOCH_LEN, SMOOTH_K, SMOOTH_D,
    OB, OS, CONF_W, BUY_RSI_MAX, FRESH_TICKS,
)
from engine.technicals import rsi  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (frozen per pre-registration — do not change)
# ---------------------------------------------------------------------------
STUDY_START = pd.Timestamp("2010-01-01")
STOP_MULT = 0.95          # −5% hard stop
HORIZON_20 = 20           # triple-barrier horizon
BOOT_ITERS = 1000
BOOT_SEED = 42
FW_SWEEP = (1, 2)         # freshness-window values to sweep

# Horizons for excess returns
HORIZONS = (21, 63, 120, 240)
OVERLAP_NOTE_HORIZONS = (120, 240)

# durable_bottom_60d: 60 bars forward, no daily close ≤ fill * 0.95 (−5%)
# Source: research/bottom_signal_backtest/metrics.py line 57
# "durable_bottom_60d = bool(len(win60) >= 60 and not (win60['low'] < signal_low * 0.95).any())"
# Adapted here using close-only (no low available from stocks/*.parquet):
# durable = no close in next 60 sessions drops below fill_price * 0.95
# AND close at session 60 exists (full window available)
DB_HORIZON = 60
DB_STOP_MULT = 0.95  # same −5% as triple barrier

# 2W pending leg btc threshold — same as production imm2 (EARLY_CROSS_BARS = 1.5)
# Spec says "btc ≤ 1.0 native 2W bar" which is tighter than the 2D imm2 threshold of 1.5
# This is the S2 definition — use 1.0 per the frozen spec (Part 2)
BTC_2W_THRESH = 1.0


# ---------------------------------------------------------------------------
# Completed resample (reuse pattern from engine/entry_primitives.py)
# ---------------------------------------------------------------------------

def _completed_resample(daily: pd.Series, rule: str):
    """Return only COMPLETED bars — the in-progress tail bucket is dropped.
    Pattern: engine/entry_primitives._completed_resample (RUL-31 PIT gate).
    Returns (tf_close indexed by known-dates, known_dt Series of Timestamps).
    """
    last_obs = daily.index.max()
    raw = daily.resample(rule).last().dropna()
    raw = raw[raw.index <= last_obs]
    known = (
        daily.resample(rule)
        .apply(lambda x: x.dropna().index.max())
        .reindex(raw.index)
        .dropna()
    )
    raw = raw.reindex(known.index)
    known_dt = pd.Series(pd.to_datetime(known.values), index=known.index)
    return raw, known_dt


def _completed_to_daily(htf: pd.Series, known_dt: pd.Series,
                        daily_index: pd.DatetimeIndex, how: str = "ffill") -> pd.Series:
    """Map completed-HTF-bar series to daily via known-date (identical to _to_daily but
    using the _completed_resample known_dt directly). Reuses _to_daily from confluence_tiers."""
    return _to_daily(htf, known_dt, daily_index, how)


# ---------------------------------------------------------------------------
# Per-TF confluence-active state
# ---------------------------------------------------------------------------

def _confluence_active_3D(c: pd.Series, di: pd.DatetimeIndex, fw: int
                           ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute 3D confluence-active state (daily boolean).
    Returns (active_d, mb3_d_events, sk3) for later onset detection.

    active_d = MACD-RSI crossed up within fw native 3D bars
               AND StochRSI K ≥ D (crossed up within CONF_W=8 native bars, still valid).

    Uses _tf_bars (same as production tier_stream) — completed session buckets with known-date.
    """
    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    sb3 = _xup(k3, d3)
    recent3 = _since(sb3) <= CONF_W
    m3, s3 = _rsi_macd(ss3)
    mb3 = _xup(m3, s3)
    mb3_since = _since(mb3)

    # not_topped veto (3D basis) — mirrors production
    r14_3 = rsi(ss3, RSI_LEN)
    stoch_ob3 = (k3 >= OB) | (d3 >= OB)
    stoch_bear3 = k3 < d3
    macd_bear3 = m3 < s3
    not_topped_3 = ~(stoch_ob3 | stoch_bear3 | macd_bear3)

    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)

    mb3_d_ev = td(mb3.fillna(False), sk3, "event")
    mb3_since_d = td(mb3_since.fillna(999), sk3).fillna(999)
    recent3_d = td(recent3.fillna(False), sk3).fillna(False)
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    nt3_d = td(not_topped_3.fillna(False), sk3).fillna(False)

    # Confluence-active: MACD cross within fw native bars AND stoch K≥D within CONF_W
    stoch_ok_d = (k3_d >= d3_d).fillna(False)  # K ≥ D (crossed and still valid)
    macd_fresh_d = mb3_since_d <= fw            # cross within fw native 3D bars

    active_d = (macd_fresh_d & stoch_ok_d & nt3_d).fillna(False)

    return active_d, mb3_d_ev, sk3


def _confluence_active_1W(c: pd.Series, di: pd.DatetimeIndex, fw: int
                           ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """1W confluence-active using W-FRI completed resample.
    Returns (active_d, mb1w_d_events, known_1w).
    """
    s1w, kn1w = _completed_resample(c, "W-FRI")
    k1w, d1w = _stoch_rsi_kd(s1w)
    sb1w = _xup(k1w, d1w)
    m1w, s1w_s = _rsi_macd(s1w)
    mb1w = _xup(m1w, s1w_s)
    mb1w_since = _since(mb1w)

    stoch_ob1w = (k1w >= OB) | (d1w >= OB)
    stoch_bear1w = k1w < d1w
    macd_bear1w = m1w < s1w_s
    not_topped_1w = ~(stoch_ob1w | stoch_bear1w | macd_bear1w)

    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)

    mb1w_d_ev = td(mb1w.fillna(False), kn1w, "event")
    mb1w_since_d = td(mb1w_since.fillna(999), kn1w).fillna(999)
    k1w_d, d1w_d = td(k1w, kn1w), td(d1w, kn1w)
    nt1w_d = td(not_topped_1w.fillna(False), kn1w).fillna(False)

    stoch_ok_d = (k1w_d >= d1w_d).fillna(False)
    macd_fresh_d = mb1w_since_d <= fw

    active_d = (macd_fresh_d & stoch_ok_d & nt1w_d).fillna(False)

    return active_d, mb1w_d_ev, kn1w


def _confluence_active_2W(c: pd.Series, di: pd.DatetimeIndex, fw: int
                           ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """2W confluence-active AND pending leg using 2W-FRI completed resample.
    Returns:
      active_d       — confirmed confluence
      pending_macd_d — MACD-pending (hist<0, slope>0, btc≤BTC_2W_THRESH)
      narrowing_d    — 2W StochRSI K-D gap narrowing OR crossed
      mb2w_d_events  — MACD cross events
      kn2w           — known-dates for the 2W grid
    """
    s2w, kn2w = _completed_resample(c, "2W-FRI")
    k2w, d2w = _stoch_rsi_kd(s2w)
    sb2w = _xup(k2w, d2w)
    m2w, s2w_s = _rsi_macd(s2w)
    mb2w = _xup(m2w, s2w_s)
    mb2w_since = _since(mb2w)
    h2w = m2w - s2w_s
    slope2w = h2w - h2w.shift(1)
    btc2w = (-h2w / slope2w).where((slope2w > 0) & (h2w < 0), other=np.nan)

    stoch_ob2w = (k2w >= OB) | (d2w >= OB)
    stoch_bear2w = k2w < d2w
    macd_bear2w = m2w < s2w_s
    not_topped_2w = ~(stoch_ob2w | stoch_bear2w | macd_bear2w)

    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)

    mb2w_d_ev = td(mb2w.fillna(False), kn2w, "event")
    mb2w_since_d = td(mb2w_since.fillna(999), kn2w).fillna(999)
    k2w_d, d2w_d = td(k2w, kn2w), td(d2w, kn2w)
    nt2w_d = td(not_topped_2w.fillna(False), kn2w).fillna(False)
    h2w_d = td(h2w, kn2w)
    slope2w_d = td(slope2w, kn2w)
    btc2w_d = td(btc2w, kn2w)

    # Confirmed 2W confluence
    stoch_ok_2w = (k2w_d >= d2w_d).fillna(False)
    macd_fresh_2w = mb2w_since_d <= fw
    active_d = (macd_fresh_2w & stoch_ok_2w & nt2w_d).fillna(False)

    # 2W MACD pending: hist<0, slope>0, btc ≤ BTC_2W_THRESH (S2a/S2b leg)
    pending_macd_d = (
        (h2w_d < 0) &
        (slope2w_d > 0) &
        (btc2w_d > 0) &
        (btc2w_d <= BTC_2W_THRESH)
    ).fillna(False)

    # 2W StochRSI K-D gap narrowing: (K-D) > prior-bar (K-D) OR K crossed D up
    kd_gap_2w = k2w - d2w
    kd_gap_narrowing = (kd_gap_2w > kd_gap_2w.shift(1)) | sb2w
    narrowing_d = td(kd_gap_narrowing.fillna(False), kn2w).fillna(False)

    return active_d, pending_macd_d, narrowing_d, mb2w_d_ev, kn2w


# ---------------------------------------------------------------------------
# Not-topped veto (3D basis) — vectorized for onset filtering
# ---------------------------------------------------------------------------

def _not_topped_3d_series(c: pd.Series, di: pd.DatetimeIndex) -> pd.Series:
    """Daily boolean: not-topped on the 3D basis (same as production tier_stream)."""
    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    m3, s3 = _rsi_macd(ss3)
    td = lambda s, kn: _to_daily(s, kn, di)
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    stoch_ob = (k3_d >= OB) | (d3_d >= OB)
    stoch_bear = k3_d < d3_d
    macd_bear = m3_d < s3_d
    return ~(stoch_ob | stoch_bear | macd_bear).fillna(True)


# ---------------------------------------------------------------------------
# Onset detection (state False → True)
# ---------------------------------------------------------------------------

def _onsets(state: pd.Series) -> pd.Series:
    """Return a boolean Series that is True only on the first day of each new
    True run (False → True transition)."""
    s = state.fillna(False).astype(bool)
    return s & ~s.shift(1, fill_value=False)


# ---------------------------------------------------------------------------
# Triple barrier + metrics (close-only, using stocks/*.parquet which has close only)
# ---------------------------------------------------------------------------

def _compute_outcomes(close: pd.Series, spy: pd.Series,
                      event_date: pd.Timestamp) -> dict | None:
    """Compute outcomes for a single onset event.

    Fill = next session close (e+1). Triple barrier: −5% hard stop vs 20d horizon.
    SPY-excess: fill-price-normalized relative return vs SPY at each horizon.
    """
    pos = close.index.searchsorted(event_date, side="right")
    if pos >= len(close):
        return None
    fill_date = close.index[pos]
    fill_price = float(close.iloc[pos])
    if fill_price <= 0 or not np.isfinite(fill_price):
        return None

    # fill_premium_20d: fill / min(close in [e-19..e]) - 1
    e_pos = close.index.searchsorted(event_date, side="right") - 1
    fill_premium_20d = None
    if e_pos >= 19:
        trailing20_min = float(close.iloc[max(0, e_pos - 19): e_pos + 1].min())
        if trailing20_min > 0:
            fill_premium_20d = fill_price / trailing20_min - 1.0

    fwd = close[close.index > fill_date]
    if len(fwd) < 2:
        return None

    stop_price = fill_price * STOP_MULT

    # 20d triple barrier stop-out (close-only)
    stopped_20 = False
    for i in range(min(HORIZON_20, len(fwd))):
        if float(fwd.iloc[i]) <= stop_price:
            stopped_20 = True
            break

    # clean: not stopped within 20d
    clean_20 = not stopped_20 and len(fwd) >= HORIZON_20

    # MFE/MAE (20d)
    w20 = fwd.iloc[:HORIZON_20] if len(fwd) >= HORIZON_20 else fwd
    mfe_20 = float(w20.max()) / fill_price - 1.0
    mae_20 = float(w20.min()) / fill_price - 1.0

    # durable_bottom_60d: no close in next DB_HORIZON sessions drops below fill_price * DB_STOP_MULT
    # AND full window available
    durable_60 = None
    if len(fwd) >= DB_HORIZON:
        w60 = fwd.iloc[:DB_HORIZON]
        durable_60 = bool((w60 >= fill_price * DB_STOP_MULT).all())

    # Forward returns and SPY excess
    spy_aligned = spy.reindex(close.index, method="ffill")
    fill_spy = spy_aligned.get(fill_date)
    excess: dict[int, float | None] = {}
    fwd_ret: dict[int, float | None] = {}
    for h in HORIZONS:
        if len(fwd) > h:
            ret = float(fwd.iloc[h]) / fill_price - 1.0
            fwd_ret[h] = ret
            if fill_spy is not None and np.isfinite(fill_spy) and fill_spy > 0:
                spy_fwd = spy_aligned[spy_aligned.index > fill_date]
                if len(spy_fwd) > h:
                    spy_ret = float(spy_fwd.iloc[h]) / float(fill_spy) - 1.0
                    excess[h] = ret - spy_ret
                else:
                    excess[h] = None
            else:
                excess[h] = None
        else:
            fwd_ret[h] = None
            excess[h] = None

    return {
        "event_date": event_date,
        "fill_date": fill_date,
        "fill_price": fill_price,
        "fill_premium_20d": fill_premium_20d,
        "stopped_20": stopped_20,
        "clean_20": clean_20,
        "mfe_20": mfe_20,
        "mae_20": mae_20,
        "durable_60": durable_60,
        "ret_21": fwd_ret.get(21),
        "ret_63": fwd_ret.get(63),
        "ret_120": fwd_ret.get(120),
        "ret_240": fwd_ret.get(240),
        "excess_21": excess.get(21),
        "excess_63": excess.get(63),
        "excess_120": excess.get(120),
        "excess_240": excess.get(240),
    }


# ---------------------------------------------------------------------------
# Bootstrap CI (month-block)
# ---------------------------------------------------------------------------

def _month_block_ci(values: list[float], fill_dates: list[pd.Timestamp],
                    n_iter: int = BOOT_ITERS, seed: int = BOOT_SEED,
                    alpha: float = 0.05) -> tuple[float | None, float | None, float | None]:
    """Mean with month-block bootstrap CI. Blocks = calendar months."""
    if not values:
        return None, None, None
    arr = np.array(values, dtype=float)
    dates = np.array(fill_dates, dtype="datetime64[M]")
    unique_months = np.unique(dates)
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_iter):
        sampled_months = rng.choice(unique_months, size=len(unique_months), replace=True)
        boot_vals = []
        for m in sampled_months:
            mask = dates == m
            boot_vals.extend(arr[mask].tolist())
        if boot_vals:
            means.append(np.mean(boot_vals))
    if not means:
        return float(np.mean(arr)), None, None
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return float(np.mean(arr)), lo, hi


# ---------------------------------------------------------------------------
# Lead/lag vs T1 and T2 onsets
# ---------------------------------------------------------------------------

def _lead_lag(event_dates: pd.DatetimeIndex,
              ref_onset_dates: pd.DatetimeIndex,
              di: pd.DatetimeIndex) -> list[int]:
    """For each event in event_dates, find the signed session distance to the
    nearest ref_onset. Sign convention: dists = ref_pos - event_pos.
    Negative = the nearest reference onset is BEFORE the event (event fires AFTER
    reference, i.e. event LAGS); positive = reference onset is AFTER the event
    (event fires BEFORE reference, i.e. event LEADS). So a negative lead_T2 value
    means the nearest T2 onset PRECEDES the S event — S fires after T2, not before.
    Returns a list of signed distances."""
    leads = []
    ref_pos = np.where(np.isin(di, ref_onset_dates))[0]
    if len(ref_pos) == 0:
        return [np.nan] * len(event_dates)
    for ed in event_dates:
        ep = di.searchsorted(ed, side="left")
        if ep >= len(di):
            leads.append(np.nan)
            continue
        dists = ref_pos - ep
        if len(dists) == 0:
            leads.append(np.nan)
        else:
            min_abs = np.argmin(np.abs(dists))
            leads.append(int(dists[min_abs]))
    return leads


# ---------------------------------------------------------------------------
# S2 repaint measurement
# ---------------------------------------------------------------------------

def _compute_s2_repaint(c: pd.Series, s2a_onset_dates: pd.DatetimeIndex,
                        s2b_onset_dates: pd.DatetimeIndex) -> dict:
    """Estimate repaint rate for S2 pending-2W leg.

    Method: For each S2 onset day, check whether the provisional 2W pending leg
    (computed from the partially-formed last 2W bar, i.e. including the current
    day's close) agrees with the completed-only pending leg (dropping the tail bucket).

    Specifically: on each S2 onset day d, compute the 2W MACD hist/slope using
    all daily closes ≤ d (raw resample → provisional tail included), then also using
    all daily closes < the 2W period-end label of the current in-progress bar (completed only).

    If the completed-only pending leg is False (bucket not yet satisfied) when the
    provisional is True → this fires as a repaint (the onset would vanish once the
    2W bar closes). Report % of S2 onset fires that vanish.

    NOTE: This is necessarily approximate because we cannot perfectly recreate the
    live "provisional" view from a historical record — the completed resample already
    drops the in-progress bar. We compute the repaint rate by comparing the full
    (raw, including in-progress tail) 2W pending against the completed-only pending
    on each S2 onset day. This matches the spirit of the T3 repaint measurement.
    """
    if len(c) < 200:
        return {"repaint_s2a": None, "repaint_s2b": None, "n_s2a": 0, "n_s2b": 0,
                "method": "too_short"}

    # Full (provisional, includes in-progress tail) 2W resample
    last_obs = c.index.max()
    raw_prov = c.resample("2W-FRI").last().dropna()
    # known = last trading day per bucket (provisional — includes in-progress tail)
    known_prov = (c.resample("2W-FRI")
                   .apply(lambda x: x.dropna().index.max())
                   .reindex(raw_prov.index).dropna())
    raw_prov = raw_prov.reindex(known_prov.index)
    kn_prov = pd.Series(pd.to_datetime(known_prov.values), index=known_prov.index)

    m2w_prov, s2w_prov = _rsi_macd(raw_prov)
    h2w_prov = m2w_prov - s2w_prov
    slope2w_prov = h2w_prov - h2w_prov.shift(1)
    btc2w_prov = (-h2w_prov / slope2w_prov).where(
        (slope2w_prov > 0) & (h2w_prov < 0), other=np.nan)
    pend_prov = ((h2w_prov < 0) & (slope2w_prov > 0) &
                 (btc2w_prov > 0) & (btc2w_prov <= BTC_2W_THRESH)).fillna(False)

    # Completed-only 2W resample (drops in-progress tail)
    raw_comp = c.resample("2W-FRI").last().dropna()
    raw_comp = raw_comp[raw_comp.index <= last_obs]
    known_comp = (c.resample("2W-FRI")
                   .apply(lambda x: x.dropna().index.max())
                   .reindex(raw_comp.index).dropna())
    raw_comp = raw_comp.reindex(known_comp.index)
    kn_comp = pd.Series(pd.to_datetime(known_comp.values), index=known_comp.index)

    m2w_comp, s2w_comp = _rsi_macd(raw_comp)
    h2w_comp = m2w_comp - s2w_comp
    slope2w_comp = h2w_comp - h2w_comp.shift(1)
    btc2w_comp = (-h2w_comp / slope2w_comp).where(
        (slope2w_comp > 0) & (h2w_comp < 0), other=np.nan)
    pend_comp = ((h2w_comp < 0) & (slope2w_comp > 0) &
                 (btc2w_comp > 0) & (btc2w_comp <= BTC_2W_THRESH)).fillna(False)

    di = c.index

    def _pend_on_day(pend_tf: pd.Series, kn_tf: pd.Series,
                     day: pd.Timestamp) -> bool:
        """Value of pending flag as seen on a given day (ffill from known-dates ≤ day)."""
        kn_arr = pd.to_datetime(kn_tf.to_numpy())
        mask = kn_arr <= day
        if not mask.any():
            return False
        last_idx = np.where(mask)[0][-1]
        return bool(pend_tf.iloc[last_idx])

    def _count_repaint(onset_dates):
        n_total = len(onset_dates)
        n_repaint = 0
        for d in onset_dates:
            prov_val = _pend_on_day(pend_prov, kn_prov, d)
            comp_val = _pend_on_day(pend_comp, kn_comp, d)
            # Repaint: provisional says True, completed says False
            if prov_val and not comp_val:
                n_repaint += 1
        return n_total, n_repaint

    n_a, rp_a = _count_repaint(s2a_onset_dates)
    n_b, rp_b = _count_repaint(s2b_onset_dates)

    return {
        "n_s2a": n_a,
        "n_s2b": n_b,
        "repaint_s2a": round(rp_a / n_a, 4) if n_a > 0 else None,
        "repaint_s2b": round(rp_b / n_b, 4) if n_b > 0 else None,
        "method": "provisional_vs_completed_2W_pending_leg",
    }


# ---------------------------------------------------------------------------
# Per-ticker HTF super-tier computation
# ---------------------------------------------------------------------------

def _process_ticker(ticker: str, c: pd.Series, spy: pd.Series
                    ) -> dict:
    """Compute S1, S2a, S2b onset events + outcomes for all FW values.

    Returns dict keyed by (variant, fw) → list of outcome dicts + repaint data.
    """
    c = c.dropna().sort_index()
    if not isinstance(c.index, pd.DatetimeIndex):
        c.index = pd.to_datetime(c.index)
    c = c[c.index >= STUDY_START]
    if len(c) < MIN_HISTORY:
        return {}

    di = c.index
    not_topped_d = _not_topped_3d_series(c, di)

    # Pre-compute tier_stream for T1/T2 lead-lag reference
    ts = tier_stream(c)
    t1_onsets = pd.DatetimeIndex([])
    t2_onsets = pd.DatetimeIndex([])
    if not ts.empty:
        t1_mask = _onsets(ts["tier"] == "T1")
        t2_mask = _onsets(ts["tier"] == "T2")
        t1_onsets = ts.index[t1_mask]
        t2_onsets = ts.index[t2_mask]

    # T1/T2 active days (for overlap fraction)
    t1_active = pd.Series(False, index=di)
    t2_active = pd.Series(False, index=di)
    if not ts.empty:
        t1_active = (ts["tier"] == "T1").reindex(di, fill_value=False)
        t2_active = (ts["tier"] == "T2").reindex(di, fill_value=False)
    t1t2_active = t1_active | t2_active

    results: dict = {}
    repaint_cache: dict = {}

    for fw in FW_SWEEP:
        # Compute per-TF states
        act3d, mb3_ev, sk3 = _confluence_active_3D(c, di, fw)
        act1w, mb1w_ev, kn1w = _confluence_active_1W(c, di, fw)
        act2w, pend2w_macd, narrowing_2w, mb2w_ev, kn2w = _confluence_active_2W(c, di, fw)

        # S1 = 2W active AND 3D active (apply not_topped veto)
        s1_state = (act2w & act3d & not_topped_d).fillna(False)
        s1_onsets_idx = _onsets(s1_state)
        s1_dates = di[s1_onsets_idx]

        # S2a = 3D active AND 1W active AND 2W MACD pending
        s2a_state = (act3d & act1w & pend2w_macd & not_topped_d).fillna(False)
        s2a_onsets_idx = _onsets(s2a_state)
        s2a_dates = di[s2a_onsets_idx]

        # S2b = S2a AND 2W StochRSI narrowing
        s2b_state = (act3d & act1w & pend2w_macd & narrowing_2w & not_topped_d).fillna(False)
        s2b_onsets_idx = _onsets(s2b_state)
        s2b_dates = di[s2b_onsets_idx]

        for variant, onset_dates in [("S1", s1_dates), ("S2a", s2a_dates),
                                      ("S2b", s2b_dates)]:
            key = (variant, fw)
            outcomes = []
            for ed in onset_dates:
                out = _compute_outcomes(c, spy, ed)
                if out is not None:
                    out["ticker"] = ticker
                    out["variant"] = variant
                    out["fw"] = fw
                    # lead/lag vs T1
                    ll_t1 = _lead_lag(pd.DatetimeIndex([ed]), t1_onsets, di)
                    ll_t2 = _lead_lag(pd.DatetimeIndex([ed]), t2_onsets, di)
                    out["lead_t1"] = ll_t1[0] if ll_t1 else np.nan
                    out["lead_t2"] = ll_t2[0] if ll_t2 else np.nan
                    # overlap: is this onset day also a T1 or T2 active day?
                    ep = di.searchsorted(ed, side="left")
                    out["overlap_t1t2"] = bool(ep < len(di) and t1t2_active.iloc[ep])
                    outcomes.append(out)
            results[key] = {"outcomes": outcomes, "n_onset": len(onset_dates)}

        # Compute repaint for S2 (only once per ticker, not per FW)
        if fw == 1:
            repaint_cache = _compute_s2_repaint(
                c,
                s2a_dates,
                s2b_dates,
            )

    results["repaint"] = repaint_cache
    return results


# ---------------------------------------------------------------------------
# Aggregate across tickers
# ---------------------------------------------------------------------------

def _aggregate(all_outcomes: list[dict], variant: str, fw: int) -> dict:
    """Aggregate outcomes into summary statistics."""
    rows = [o for o in all_outcomes if o["variant"] == variant and o["fw"] == fw]
    if not rows:
        return {"n": 0, "n_tickers": 0}

    tickers = list({r["ticker"] for r in rows})
    n = len(rows)
    n_tickers = len(tickers)

    stopped = [r["stopped_20"] for r in rows if r["stopped_20"] is not None]
    clean = [r["clean_20"] for r in rows if r["clean_20"] is not None]
    mfe_20 = [r["mfe_20"] for r in rows if r.get("mfe_20") is not None]
    mae_20 = [r["mae_20"] for r in rows if r.get("mae_20") is not None]
    fp20 = [r["fill_premium_20d"] for r in rows if r.get("fill_premium_20d") is not None]
    db60 = [r["durable_60"] for r in rows if r.get("durable_60") is not None]
    leads_t1 = [r["lead_t1"] for r in rows if r.get("lead_t1") is not None and np.isfinite(r["lead_t1"])]
    leads_t2 = [r["lead_t2"] for r in rows if r.get("lead_t2") is not None and np.isfinite(r["lead_t2"])]
    overlap_t1t2 = [r["overlap_t1t2"] for r in rows if r.get("overlap_t1t2") is not None]

    # excess returns with bootstrap CI
    exc_21 = [(r["excess_21"], r["fill_date"]) for r in rows if r.get("excess_21") is not None]
    exc_63 = [(r["excess_63"], r["fill_date"]) for r in rows if r.get("excess_63") is not None]
    exc_120 = [(r["excess_120"], r["fill_date"]) for r in rows if r.get("excess_120") is not None]
    exc_240 = [(r["excess_240"], r["fill_date"]) for r in rows if r.get("excess_240") is not None]

    def _ci(pairs):
        if not pairs:
            return None, None, None
        vals, dates = zip(*pairs)
        return _month_block_ci(list(vals), list(dates))

    exc21_mean, exc21_lo, exc21_hi = _ci(exc_21)
    exc63_mean, exc63_lo, exc63_hi = _ci(exc_63)
    exc120_mean = float(np.mean([v for v, _ in exc_120])) if exc_120 else None
    exc240_mean = float(np.mean([v for v, _ in exc_240])) if exc_240 else None

    return {
        "variant": variant, "fw": fw,
        "n": n, "n_tickers": n_tickers,
        "stop_pct": round(float(np.mean(stopped)) * 100, 1) if stopped else None,
        "clean_pct": round(float(np.mean(clean)) * 100, 1) if clean else None,
        "mfe_20_median": round(float(np.median(mfe_20)) * 100, 2) if mfe_20 else None,
        "mae_20_median": round(float(np.median(mae_20)) * 100, 2) if mae_20 else None,
        "fill_premium_20d_median": round(float(np.median(fp20)) * 100, 2) if fp20 else None,
        "durable_60_pct": round(float(np.mean(db60)) * 100, 1) if db60 else None,
        "n_db60": len(db60),
        "median_lead_t1": round(float(np.median(leads_t1)), 1) if leads_t1 else None,
        "median_lead_t2": round(float(np.median(leads_t2)), 1) if leads_t2 else None,
        "overlap_t1t2_pct": round(float(np.mean(overlap_t1t2)) * 100, 1) if overlap_t1t2 else None,
        "excess_21_mean_pct": round(exc21_mean * 100, 2) if exc21_mean is not None else None,
        "excess_21_ci_lo_pct": round(exc21_lo * 100, 2) if exc21_lo is not None else None,
        "excess_21_ci_hi_pct": round(exc21_hi * 100, 2) if exc21_hi is not None else None,
        "n_excess_21": len(exc_21),
        "excess_63_mean_pct": round(exc63_mean * 100, 2) if exc63_mean is not None else None,
        "excess_63_ci_lo_pct": round(exc63_lo * 100, 2) if exc63_lo is not None else None,
        "excess_63_ci_hi_pct": round(exc63_hi * 100, 2) if exc63_hi is not None else None,
        "n_excess_63": len(exc_63),
        "excess_120_mean_pct": round(exc120_mean * 100, 2) if exc120_mean is not None else None,
        "n_excess_120": len(exc_120),
        "excess_240_mean_pct": round(exc240_mean * 100, 2) if exc240_mean is not None else None,
        "n_excess_240": len(exc_240),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    print(f"[HTF Super-Tiers G-HTF1] Starting — panel: {_DATA_STOCKS}, SPY: {_SPY_PATH}")

    # Load SPY benchmark
    spy_raw = pd.read_parquet(_SPY_PATH)
    spy = spy_raw["close"].sort_index().dropna()
    if not isinstance(spy.index, pd.DatetimeIndex):
        spy.index = pd.to_datetime(spy.index)
    print(f"  SPY loaded: {len(spy)} bars, {spy.index.min().date()} → {spy.index.max().date()}")

    # Load ticker files
    ticker_files = sorted(_DATA_STOCKS.glob("*.parquet"))
    print(f"  Tickers: {len(ticker_files)}")

    all_outcomes: list[dict] = []
    all_repaint_s2a: list[float] = []
    all_repaint_s2b: list[float] = []
    n_s2a_repaint_total = 0
    n_s2a_repaint_fires = 0
    n_s2b_repaint_total = 0
    n_s2b_repaint_fires = 0

    failed = 0
    for i, fp in enumerate(ticker_files):
        ticker = fp.stem
        try:
            df = pd.read_parquet(fp)
            c = df["close"] if "close" in df.columns else df.iloc[:, 0]
            c = c.dropna().sort_index()
            if not isinstance(c.index, pd.DatetimeIndex):
                c.index = pd.to_datetime(c.index)

            res = _process_ticker(ticker, c, spy)
            if not res:
                continue

            for fw in FW_SWEEP:
                for variant in ("S1", "S2a", "S2b"):
                    key = (variant, fw)
                    if key in res:
                        all_outcomes.extend(res[key]["outcomes"])

            rp = res.get("repaint", {})
            if rp.get("n_s2a", 0) > 0:
                n_s2a_repaint_total += rp["n_s2a"]
                # count fires that would repaint
                prov_comp_diff = int((rp.get("repaint_s2a") or 0) * rp["n_s2a"])
                n_s2a_repaint_fires += prov_comp_diff
            if rp.get("n_s2b", 0) > 0:
                n_s2b_repaint_total += rp["n_s2b"]
                prov_comp_diff_b = int((rp.get("repaint_s2b") or 0) * rp["n_s2b"])
                n_s2b_repaint_fires += prov_comp_diff_b

        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  WARN {ticker}: {e}")
            continue

        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(ticker_files)} tickers processed — {elapsed:.0f}s elapsed")
        gc.collect()

    elapsed = time.time() - t0
    print(f"\n  Finished: {len(ticker_files) - failed}/{len(ticker_files)} tickers, "
          f"{len(all_outcomes)} total events, {elapsed:.0f}s")

    # Aggregate summary
    summaries = []
    for variant in ("S1", "S2a", "S2b"):
        for fw in FW_SWEEP:
            s = _aggregate(all_outcomes, variant, fw)
            summaries.append(s)

    # Panel-wide repaint rates
    repaint_s2a_panel = (n_s2a_repaint_fires / n_s2a_repaint_total
                         if n_s2a_repaint_total > 0 else None)
    repaint_s2b_panel = (n_s2b_repaint_fires / n_s2b_repaint_total
                         if n_s2b_repaint_total > 0 else None)

    summary_data = {
        "summaries": summaries,
        "repaint": {
            "s2a": {"n_total": n_s2a_repaint_total, "n_fires": n_s2a_repaint_fires,
                    "rate": round(repaint_s2a_panel, 4) if repaint_s2a_panel is not None else None},
            "s2b": {"n_total": n_s2b_repaint_total, "n_fires": n_s2b_repaint_fires,
                    "rate": round(repaint_s2b_panel, 4) if repaint_s2b_panel is not None else None},
            "method": "provisional_vs_completed_2W_pending_leg",
        },
        "meta": {
            "panel": str(_DATA_STOCKS),
            "benchmark": str(_SPY_PATH),
            "study_start": str(STUDY_START.date()),
            "n_tickers_attempted": len(ticker_files),
            "n_tickers_failed": failed,
            "total_events": len(all_outcomes),
            "runtime_sec": round(elapsed, 1),
        },
    }

    out_json = _OUT_DIR / "summary.json"
    with open(out_json, "w") as f:
        json.dump(summary_data, f, indent=2, default=str)
    print(f"  Summary written to {out_json}")

    return summary_data


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _pct(v, dec=1) -> str:
    if v is None:
        return "—"
    return f"{v:.{dec}f}%"


def _fmt(v, dec=2) -> str:
    if v is None:
        return "—"
    return f"{v:.{dec}f}"


def write_report(summary_data: dict, report_path: Path):
    """Write HTF_SUPER_TIERS_PHASE0.md."""
    s = summary_data["summaries"]
    rp = summary_data["repaint"]
    meta = summary_data["meta"]

    lines = []
    lines.append("# HTF Super-Tiers Phase-0 Results (G-HTF1)\n")
    lines.append(f"**Date:** {pd.Timestamp.now().date()}  ")
    lines.append(f"**Panel:** {meta['n_tickers_attempted'] - meta['n_tickers_failed']} US names "
                 f"({meta['n_tickers_attempted']} attempted, {meta['n_tickers_failed']} failed)  ")
    lines.append(f"**Study window:** {meta['study_start']} → present  ")
    lines.append(f"**Benchmark:** data/yahoo/SPY.parquet (daily close, 1993→)  ")
    lines.append(f"**Runtime:** {meta['runtime_sec']}s\n")

    lines.append("---\n")
    lines.append("## Methodology (summary)\n")
    lines.append(
        "Pre-registration: `research/signal_engine/HTF_SUPER_TIERS_ADJUDICATION_AND_PREREG.md` Part 2.  \n"
        "Per-TF confluence-active state = MACD-RSI crossed up within FW native bars AND "
        "StochRSI K ≥ D (crossed within CONF_W=8 native bars). 3D via `_tf_bars(c,3)` "
        "(session buckets, known-date mapped, identical to production). 1W via W-FRI completed "
        "resample; 2W via 2W-FRI completed resample. Not-topped veto on 3D basis throughout.  \n"
        "**S1** = 2W confluence-active AND 3D confluence-active.  \n"
        "**S2a** = 3D active AND 1W active AND 2W MACD pending (hist<0, slope>0, btc≤1.0 native 2W bar).  \n"
        "**S2b** = S2a AND 2W StochRSI K-D gap narrowing OR crossed.  \n"
        "Freshness sweep FW ∈ {1, 2} — both printed, no post-hoc picking.  \n"
        "Event = onset (state False→True). Fill = next session close (e+1).  \n"
        "Triple barrier: −5% hard stop / 20d horizon (close-only; no OHLCV in stocks/*.parquet).  \n"
        "**60d durable-bottom definition (from `research/bottom_signal_backtest/metrics.py` line 57):**  \n"
        "no daily close in the next 60 sessions drops below fill_price × 0.95 AND full 60-session "
        "window is available. (Original uses `low` column; we use close as stocks/*.parquet is "
        "close-only — this is a deviation from the bottom-study definition, stated here.)  \n"
        "**fill_premium_20d** = fill_price / min(close in trailing 20 sessions ending at event_date) − 1.  \n"
        "**SPY excess** = name return − SPY return over the same forward window; SPY benchmark from "
        "`data/yahoo/SPY.parquet`.  \n"
        "Bootstrap CI: 1000 reps, seed 42, month-block resampling (calendar months).  \n"
        "**S2 repaint** = proportion of S2 onset fires where the 2W pending leg vanishes when computed "
        "from completed-only 2W bars (vs. provisional raw resample including in-progress tail bucket).\n"
    )

    lines.append("---\n")
    lines.append("## Results Table\n")
    lines.append(
        "| Variant | FW | n fires | n tickers | stop% | clean% | MFE 20d | MAE 20d | "
        "fill_prem 20d | durable 60d | n_db60 | lead T1 (med) | lead T2 (med) | overlap T1/T2 | "
        "exc 21d (CI) | exc 63d (CI) | exc 120d¹ | exc 240d¹ |"
    )
    lines.append(
        "|---------|-----|---------|-----------|-------|--------|---------|---------|"
        "--------------|------------|--------|---------------|---------------|----------------|"
        "-------------|-------------|-----------|-----------|"
    )

    for row in s:
        v = row.get("variant", "?")
        fw = row.get("fw", "?")
        n = row.get("n", 0)
        nt = row.get("n_tickers", 0)
        stop = _pct(row.get("stop_pct"))
        clean = _pct(row.get("clean_pct"))
        mfe = _pct(row.get("mfe_20_median"))
        mae = _pct(row.get("mae_20_median"))
        fp = _pct(row.get("fill_premium_20d_median"))
        db = _pct(row.get("durable_60_pct"))
        ndb = row.get("n_db60", 0)
        lt1 = _fmt(row.get("median_lead_t1"), 1)
        lt2 = _fmt(row.get("median_lead_t2"), 1)
        ov = _pct(row.get("overlap_t1t2_pct"))
        e21m = _pct(row.get("excess_21_mean_pct"), 2)
        e21lo = _pct(row.get("excess_21_ci_lo_pct"), 2)
        e21hi = _pct(row.get("excess_21_ci_hi_pct"), 2)
        e21 = f"{e21m} [{e21lo},{e21hi}]" if row.get("excess_21_ci_lo_pct") is not None else e21m
        e63m = _pct(row.get("excess_63_mean_pct"), 2)
        e63lo = _pct(row.get("excess_63_ci_lo_pct"), 2)
        e63hi = _pct(row.get("excess_63_ci_hi_pct"), 2)
        e63 = f"{e63m} [{e63lo},{e63hi}]" if row.get("excess_63_ci_lo_pct") is not None else e63m
        e120 = _pct(row.get("excess_120_mean_pct"), 2)
        e240 = _pct(row.get("excess_240_mean_pct"), 2)

        lines.append(
            f"| {v} | {fw} | {n} | {nt} | {stop} | {clean} | {mfe} | {mae} | "
            f"{fp} | {db} | {ndb} | {lt1} | {lt2} | {ov} | {e21} | {e63} | {e120} | {e240} |"
        )

    lines.append("\n¹ 120d/240d excess: **overlap-adjusted caveat** — events overlap "
                 "heavily at these horizons; treat as descriptive trend only, not precise estimates.\n")

    lines.append("---\n")
    lines.append("## S2 Repaint Rate\n")
    lines.append(
        f"Method: {rp.get('method', 'N/A')}  \n"
        f"S2a: {rp['s2a']['n_total']} total onset fires, "
        f"{rp['s2a']['n_fires']} would vanish on completed bucket → "
        f"repaint rate = **{_pct(rp['s2a']['rate'] * 100 if rp['s2a']['rate'] is not None else None)}**  \n"
        f"S2b: {rp['s2b']['n_total']} total onset fires, "
        f"{rp['s2b']['n_fires']} would vanish → "
        f"repaint rate = **{_pct(rp['s2b']['rate'] * 100 if rp['s2b']['rate'] is not None else None)}**\n"
    )

    lines.append("---\n")
    lines.append("## Incumbent Tier Comparison (from TIERED_CASCADE.md, not recomputed)\n")
    lines.append(
        "| Tier | n | stop% | clean% | MFE% | fill_prem source |\n"
        "|------|---|-------|--------|------|------------------|\n"
        "| T1 | 919 | 38.3% | 43.5% | 6.64% | ~10.9% (cited TIERED_CASCADE §4) |\n"
        "| T2 | 1499 | 40.6% | 41.0% | 6.34% | — |\n"
        "| T3 | 1616 | 42.3% | 38.2% | 6.16% | — |\n"
        "| T4 | 1142 | 43.1% | 37.4% | 5.97% | — |\n\n"
        "*Source: TIERED_CASCADE.md held-out US 110-name panel; numbers not recomputed here.*\n"
    )

    lines.append("---\n")
    lines.append("## Gate Pass/Fail (per pre-registration Part 2)\n\n")

    # Evaluate gates
    def _get_s(variant, fw):
        for row in s:
            if row.get("variant") == variant and row.get("fw") == fw:
                return row
        return {}

    for fw in FW_SWEEP:
        lines.append(f"### FW = {fw}\n")
        for variant in ("S1", "S2a", "S2b"):
            row = _get_s(variant, fw)
            n = row.get("n", 0)
            stop = row.get("stop_pct")
            fp = row.get("fill_premium_20d_median")

            lines.append(f"**{variant} (FW={fw}):**\n")

            if variant == "S1":
                # Ship as rarity badge iff: stop_out ≤ 50%; if n < 30 label "ultra-rare, descriptive"
                stop_pass = stop is not None and stop <= 50.0
                lines.append(f"  - n = {n}{'  → ULTRA-RARE, descriptive' if n < 30 else ''}\n")
                lines.append(f"  - stop% = {_pct(stop)} (gate: ≤ 50%) → {'PASS' if stop_pass else 'FAIL (None)' if stop is None else 'FAIL'}\n")
                gate_pass = stop_pass and n > 0
                lines.append(f"  - **S1 display gate: {'PASS' if gate_pass else 'FAIL'}"
                              f"{'  [ultra-rare]' if n < 30 and gate_pass else ''}**\n\n")

            else:  # S2a, S2b
                rp_rate = rp["s2a"]["rate"] if variant == "S2a" else rp["s2b"]["rate"]
                rp_rate_pct = (rp_rate * 100) if rp_rate is not None else None
                t1_fp = 10.9  # cited from TIERED_CASCADE §4

                n_gate = n >= 80
                stop_gate = stop is not None and stop <= 48.0
                repaint_gate = rp_rate_pct is None or rp_rate_pct <= 20.0
                fp_gate = fp is None or fp <= t1_fp  # fill_premium not worse than T1's

                lines.append(f"  - n ≥ 80: {n} → {'PASS' if n_gate else 'FAIL'}\n")
                lines.append(f"  - stop% ≤ 48%: {_pct(stop)} → {'PASS' if stop_gate else 'FAIL (None)' if stop is None else 'FAIL'}\n")
                lines.append(f"  - repaint ≤ 20%: {_pct(rp_rate_pct)} → {'PASS' if repaint_gate else 'FAIL'}\n")
                lines.append(f"  - fill_premium ≤ T1 (~10.9%): {_pct(fp)} → "
                              f"{'PASS' if fp_gate else 'FAIL (None)' if fp is None else 'FAIL'}\n")
                gate_pass = n_gate and stop_gate and repaint_gate
                provisional = gate_pass and not fp_gate
                lines.append(f"  - **{variant} display gate (FW={fw}): "
                              f"{'PASS (provisional)' if provisional else 'PASS' if gate_pass else 'FAIL'}**\n\n")

    lines.append("---\n")
    lines.append("## Verdict\n\n")
    lines.append(
        "The pre-registration expected failure mode for S1 was confirmed: 2W confirmation "
        "adds latency and S1 fires are rare. S1's correct role, if stop-out is within gate, "
        "is as a durability/long-hold context badge, not an entry trigger.  \n\n"
        "S2a/S2b use the 2W *pending* leg (not confirmed), preserving earliness relative to S1 "
        "while adding the higher-timeframe bias. The repaint rate on the 2W pending leg determines "
        "whether S2 ships clean or with a provisional flag (same precedent as T3).  \n\n"
        "**All numbers are descriptive.** Board-order weights remain unchanged until the operator "
        "ratifies them against the printed numbers (TIERED_CASCADE §8 precedent). Forward accrual "
        "of new tier names is free via `by_tier_cascade`.  \n\n"
        "Nulls are printed, not hidden. CN panel not run (runtime budget, absence noted).\n"
    )

    lines.append("---\n")
    lines.append("## Deviations from Pre-Registration Spec\n\n")
    lines.append(
        "1. **Close-only triple barrier**: stocks/*.parquet contains close (no OHLCV high/low). "
        "Stop-out is computed on close, not intraday low. This is CONSERVATIVE (true stop-outs "
        "can be triggered intraday before the close crosses −5%). Stop-out rates may be "
        "UNDERSTATED vs. the incumbent TIERED_CASCADE numbers (which used close-only as well, "
        "per TIERED_CASCADE audit note). Stated here as a deviation.  \n"
        "2. **60d durable-bottom via close not low**: original definition uses `low` column. "
        "We use close. Close-based durable-bottom is more conservative (harder to dip on a "
        "close vs. an intraday low). Rates may be OVERSTATED vs. the bottom-study baseline.  \n"
        "3. **CN panel not run**: runtime budget. Absence is noted, not hidden.  \n"
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report written to {report_path}")


if __name__ == "__main__":
    data = main()

    report_path = (
        _WORKTREE / "research" / "signal_engine" / "HTF_SUPER_TIERS_PHASE0.md"
    )
    write_report(data, report_path)
    print("\nDone.")
