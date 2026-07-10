"""engine/intraday_flow.py — Intraday Flow Tracker pure-function engine (IFT A1).

Pure-function layer; zero I/O, zero LLM. All metrics are deterministic.
Display-tier only (CONST-ART1/CONST-ART2).

Honesty labels:
  - RVOL_tod and volume-durability metrics are price/volume context only.
  - ~net call premium (NCP) direction reads carry a ~-soft label per RUL-F3.12.
  - Compliance: DT-R11b — dt_contra excluded from confluence_legs.
  - Compliance: composite-law / Signal Commons R3 — K-of-N boolean count only.

Sibling: engine/flow_velocity.py (kinetics primitive ported here for NCP velocity).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from engine import indicators
from engine import bollinger_event_signals as _bes

log = logging.getLogger(__name__)

# ── NCP velocity config (mirrors flow_velocity._AGG / _kinetics tuning) ─────
_NCP_VEL_CFG: dict = {
    "slope_window": 15,        # trailing minutes for slope (15-min window)
    "baseline_window": 60,     # session baseline for vol normalisation
    "min_obs": 10,             # minimum data points before scoring
}


# ── 1. Volume-share baseline curve ──────────────────────────────────────────

def vol_share_curve(bars_by_session: list[list[dict]]) -> list[float] | None:
    """Compute the median hourly expected cumulative-volume-share curve.

    Each session in ``bars_by_session`` is a list of hourly bar dicts
    with at least a ``volume`` field.  The output has length equal to the
    number of hours in the trading day (up to 7 for a regular 9:30-16:00 ET
    session) — position i is the median cumulative fraction of daily volume
    that should have traded through the end of hour i.

    Args:
        bars_by_session: List of sessions, each a list of hourly bar dicts
            with a ``volume`` key.  Minimum 2 sessions required; returns None
            when fewer are provided or when all sessions have zero volume.

    Returns:
        List of floats in [0, 1] (length = n_hours) or None.

    Defensive: sessions with zero total volume are skipped; hours beyond
    the shortest session are padded to 1.0.
    """
    if not bars_by_session or len(bars_by_session) < 2:
        return None

    curves: list[list[float]] = []
    for sess in bars_by_session:
        if not sess:
            continue
        vols = [float(b.get("volume") or 0) for b in sess]
        total = sum(vols)
        if total <= 0:
            continue
        cum = 0.0
        shares: list[float] = []
        for v in vols:
            cum += v
            shares.append(min(cum / total, 1.0))
        curves.append(shares)

    if len(curves) < 2:
        return None

    # Align to the most common hour-count, padding short sessions to 1.0.
    n_hours = max(len(c) for c in curves)
    padded = [(c + [1.0] * (n_hours - len(c))) for c in curves]

    # Median per hour-position over the trailing sessions.
    result: list[float] = []
    for h in range(n_hours):
        vals = [p[h] for p in padded]
        result.append(float(np.median(vals)))
    return result


# ── 2. Relative volume (time-of-day adjusted) ────────────────────────────────

def rvol_tod(
    cum_vol_today: float | None,
    adv20_shares: float | None,
    expected_share: float | None,
) -> float | None:
    """Compute RVOL_tod = cum_vol_today / (adv20_shares × expected_share).

    Args:
        cum_vol_today: Cumulative shares traded today so far.
        adv20_shares: 20-session average daily volume in shares.
        expected_share: Expected cumulative volume fraction at this time-of-day
            (from vol_share_curve, in [0, 1]).

    Returns:
        Float >= 0, or None when any input is None / zero.
    """
    if cum_vol_today is None or adv20_shares is None or expected_share is None:
        return None
    if adv20_shares <= 0 or expected_share <= 0:
        return None
    expected_abs = adv20_shares * expected_share
    if expected_abs <= 0:
        return None
    return round(float(cum_vol_today) / expected_abs, 3)


# ── 3. Session VWAP ──────────────────────────────────────────────────────────

def session_vwap(today_bars: list[dict]) -> float | None:
    """Compute the session VWAP from hourly bars (OHLCV).

    Uses the typical price (H+L+C)/3 × volume for each bar.

    Args:
        today_bars: List of hourly bar dicts with keys ``high``, ``low``,
            ``close``, ``volume``.

    Returns:
        VWAP as a float, or None when bars are empty or total volume is zero.
    """
    if not today_bars:
        return None
    pv_sum = 0.0
    vol_sum = 0.0
    for b in today_bars:
        h = b.get("high")
        lo = b.get("low")
        c = b.get("close")
        v = b.get("volume")
        if h is None or lo is None or c is None or v is None:
            continue
        try:
            typical = (float(h) + float(lo) + float(c)) / 3.0
            vol = float(v)
        except (TypeError, ValueError):
            continue
        pv_sum += typical * vol
        vol_sum += vol
    if vol_sum <= 0:
        return None
    return round(pv_sum / vol_sum, 4)


# ── 4. Volume durability ─────────────────────────────────────────────────────

def volume_durability(
    today_bars: list[dict],
    baseline_curve: list[float] | None,
    adv20_shares: float | None = None,
) -> float | None:
    """Share of hourly bars that close in their upper half AND have volume >= TOD baseline.

    "Upper half of bar" = close >= (high + low) / 2.
    "Volume >= TOD baseline" = bar volume >= (adv20_shares × expected_incremental_vol_for_that_hour).

    When adv20_shares or baseline_curve is None, falls back to the close-in-upper-half
    fraction only (still a durability read, just without the volume gate).

    Args:
        today_bars: List of hourly bar dicts with ``open``, ``high``, ``low``,
            ``close``, ``volume``.
        baseline_curve: Cumulative volume-share curve from vol_share_curve().
        adv20_shares: 20-session ADV in shares (for incremental vol baseline).

    Returns:
        Float in [0, 1], or None when today_bars is empty.
    """
    if not today_bars:
        return None

    # Build incremental expected volume per bar from cumulative curve.
    inc_baseline: list[float | None] = []
    if baseline_curve is not None and adv20_shares is not None and adv20_shares > 0:
        prev = 0.0
        for i in range(len(today_bars)):
            if i < len(baseline_curve):
                share = baseline_curve[i]
                inc_baseline.append(adv20_shares * max(share - prev, 0.0))
                prev = share
            else:
                inc_baseline.append(None)
    else:
        inc_baseline = [None] * len(today_bars)

    qualifying = 0
    total = 0
    for i, b in enumerate(today_bars):
        h = b.get("high")
        lo = b.get("low")
        c = b.get("close")
        v = b.get("volume")
        if h is None or lo is None or c is None:
            continue
        try:
            h_f, lo_f, c_f = float(h), float(lo), float(c)
        except (TypeError, ValueError):
            continue
        total += 1
        mid = (h_f + lo_f) / 2.0
        upper_half = c_f >= mid
        # Volume gate: only applied when baseline is available.
        vol_ok = True
        exp = inc_baseline[i] if i < len(inc_baseline) else None
        if exp is not None and v is not None:
            try:
                vol_ok = float(v) >= exp
            except (TypeError, ValueError):
                vol_ok = True
        if upper_half and vol_ok:
            qualifying += 1

    if total == 0:
        return None
    return round(qualifying / total, 3)


# ── 5. Higher lows ───────────────────────────────────────────────────────────

def higher_lows(today_bars: list[dict]) -> int:
    """Count consecutive higher lows from the first bar of the session.

    Returns the number of bars (after the first) whose ``low`` exceeds the
    previous bar's ``low``, stopping at the first violation.

    Args:
        today_bars: List of hourly bar dicts with a ``low`` key.

    Returns:
        Integer >= 0.  Returns 0 for empty or single-bar sessions.
    """
    if len(today_bars) < 2:
        return 0
    lows: list[float] = []
    for b in today_bars:
        lo = b.get("low")
        if lo is None:
            continue
        try:
            lows.append(float(lo))
        except (TypeError, ValueError):
            continue
    count = 0
    for i in range(1, len(lows)):
        if lows[i] > lows[i - 1]:
            count += 1
        else:
            break
    return count


# ── 6. NCP velocity (slope-z kinetics, ported from engine/flow_velocity.py) ──

def ncp_velocity(
    minutes_series: list[float | None],
    slope_window: int | None = None,
    baseline_window: int | None = None,
) -> float | None:
    """Slope-z of cumulative NCP vs session mean pace.

    Ported from engine/flow_velocity._kinetics: velocity = t-stat of the
    trailing slope_window drift of cumulative NCP vs baseline_window vol.

    Args:
        minutes_series: Per-minute cumulative NCP values (may contain None).
        slope_window: Trailing window for slope (default: _NCP_VEL_CFG["slope_window"]).
        baseline_window: Baseline window for vol (default: _NCP_VEL_CFG["baseline_window"]).

    Returns:
        Float z-score, or None when fewer than min_obs non-null values.
    """
    sw = slope_window or _NCP_VEL_CFG["slope_window"]
    bw = baseline_window or _NCP_VEL_CFG["baseline_window"]
    min_obs = _NCP_VEL_CFG["min_obs"]

    if not minutes_series:
        return None

    s = pd.Series([v for v in minutes_series], dtype=float)
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < min_obs:
        return None

    # cumsum gives the cumulative NCP trajectory; slope_z measures its drift rate.
    z_series = indicators.slope_z(s.cumsum(), sw, bw, use_log=False)
    if len(z_series.dropna()) == 0:
        return None
    v = z_series.iloc[-1]
    return round(float(v), 3) if np.isfinite(v) else None


# ── 7. Flow durability ────────────────────────────────────────────────────────

def flow_durability(
    minutes_series: list[float | None],
    window_min: int = 5,
) -> dict:
    """Share of N-minute windows with positive NCP + longest streak.

    Groups the per-minute cumulative NCP series into non-overlapping windows
    of ``window_min`` minutes and counts windows where the INCREMENTAL NCP
    (end_of_window − start_of_window) is positive.

    Args:
        minutes_series: Per-minute cumulative NCP (may contain None).
        window_min: Window size in minutes (default 5).

    Returns:
        Dict with keys:
          - ``positive_share`` (float in [0,1] or None): fraction of windows positive.
          - ``longest_streak`` (int or None): max consecutive positive windows.
    """
    null_result: dict = {"positive_share": None, "longest_streak": None}
    if not minutes_series:
        return null_result

    vals: list[float] = []
    for v in minutes_series:
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue

    if len(vals) < window_min:
        return null_result

    # Build incremental windows.
    windows: list[bool] = []
    step = window_min
    for start in range(0, len(vals) - step + 1, step):
        end = start + step
        delta = vals[end - 1] - vals[start]
        windows.append(delta > 0)

    if not windows:
        return null_result

    positive_share = round(sum(windows) / len(windows), 3)

    # Longest streak.
    longest = 0
    current = 0
    for w in windows:
        if w:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return {"positive_share": positive_share, "longest_streak": longest}


# ── 8. Confluence legs ────────────────────────────────────────────────────────

@dataclass
class ConfluenceLegs:
    """Seven boolean confluence legs + K count (IFT §2.5).

    All fields are independently inspectable; no composite score.
    dt_contra is EXCLUDED per DT-R11b.
    """
    # L1: washout_recent — bb_lower_reclaim ≤ washout_lookback sessions OR
    #     21d drawdown ≤ −12% with recovery begun.
    L1_washout_recent: bool | None = None
    # L2: reclaim — price > session VWAP AND price > prevClose.
    L2_reclaim: bool | None = None
    # L3: rvol_elevated — RVOL_tod >= rvol_confirm threshold.
    L3_rvol_elevated: bool | None = None
    # L4: vol_durable — volume_durability >= durability_min.
    L4_vol_durable: bool | None = None
    # L5: flow_bid — ~net call prem > 0 AND flow_durability >= durability_min.
    #     (~-soft per RUL-F3.12).
    L5_flow_bid: bool | None = None
    # L6: upturn_organ — mtf_upturn state >= UPTURN_WATCH.
    L6_upturn_organ: bool | None = None
    # L7: leader_quality — NOT failed_breakout_trap.
    L7_leader_quality: bool | None = None
    # K = count of True legs (None legs treated as absent).
    K: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.K = sum(
            1 for v in [
                self.L1_washout_recent,
                self.L2_reclaim,
                self.L3_rvol_elevated,
                self.L4_vol_durable,
                self.L5_flow_bid,
                self.L6_upturn_organ,
                self.L7_leader_quality,
            ]
            if v is True
        )

    def as_dict(self) -> dict:
        return {
            "L1_washout_recent": self.L1_washout_recent,
            "L2_reclaim": self.L2_reclaim,
            "L3_rvol_elevated": self.L3_rvol_elevated,
            "L4_vol_durable": self.L4_vol_durable,
            "L5_flow_bid": self.L5_flow_bid,
            "L6_upturn_organ": self.L6_upturn_organ,
            "L7_leader_quality": self.L7_leader_quality,
            "K": self.K,
        }


def confluence_legs(
    *,
    # L1 inputs
    bb_lower_reclaim_days: int | None = None,
    drawdown_21d_pct: float | None = None,
    recovery_begun: bool | None = None,
    washout_lookback: int = 10,
    # L2 inputs
    price: float | None = None,
    vwap: float | None = None,
    prev_close: float | None = None,
    # L3 inputs
    rvol_tod_val: float | None = None,
    rvol_confirm: float = 1.30,
    # L4 inputs
    vol_durability_val: float | None = None,
    durability_min: float = 0.60,
    # L5 inputs (~-soft per RUL-F3.12)
    cum_ncp: float | None = None,
    flow_durability_val: float | None = None,
    # L6 inputs
    mtf_upturn_state: str | None = None,
    # L7 inputs
    failed_breakout_trap: bool | None = None,
) -> ConfluenceLegs:
    """Compute the seven confluence legs per design §2.5.

    All legs are independently computable; a leg is None when its required
    inputs are absent.  No composite score is produced — K is the count of
    True legs only.

    Args:
        bb_lower_reclaim_days: Sessions since the last BB lower band reclaim event.
        drawdown_21d_pct: 21-session maximum drawdown (negative float, e.g. -0.15).
        recovery_begun: True when price has started recovering from the 21d low.
        washout_lookback: Sessions threshold for L1 (default 10, from config).
        price: Current price or latest close.
        vwap: Session VWAP.
        prev_close: Previous session close.
        rvol_tod_val: Output of rvol_tod().
        rvol_confirm: Threshold for L3 (default 1.30, from config).
        vol_durability_val: Output of volume_durability().
        durability_min: Threshold for L4/L5 (default 0.60, from config).
        cum_ncp: Cumulative ~net call premium today (positive = call bid).
            (~-soft per RUL-F3.12.)
        flow_durability_val: positive_share from flow_durability().
        mtf_upturn_state: String state from mtf_upturn engine
            ("UPTURN_CONFIRMED" | "UPTURN_WATCH" | other).
        failed_breakout_trap: True when the personality classifier fired this flag.

    Returns:
        ConfluenceLegs dataclass with 7 bool fields and K count.
    """
    # ── L1: washout_recent ────────────────────────────────────────────────────
    l1: bool | None = None
    if bb_lower_reclaim_days is not None:
        l1 = bb_lower_reclaim_days <= washout_lookback
    elif drawdown_21d_pct is not None and recovery_begun is not None:
        l1 = drawdown_21d_pct <= -0.12 and recovery_begun
    # If both paths absent, l1 stays None.

    # ── L2: reclaim ───────────────────────────────────────────────────────────
    l2: bool | None = None
    if price is not None and vwap is not None and prev_close is not None:
        l2 = price > vwap and price > prev_close
    elif price is not None and vwap is not None:
        l2 = price > vwap
    elif price is not None and prev_close is not None:
        l2 = price > prev_close

    # ── L3: rvol_elevated ─────────────────────────────────────────────────────
    l3: bool | None = None
    if rvol_tod_val is not None:
        l3 = rvol_tod_val >= rvol_confirm

    # ── L4: vol_durable ───────────────────────────────────────────────────────
    l4: bool | None = None
    if vol_durability_val is not None:
        l4 = vol_durability_val >= durability_min

    # ── L5: flow_bid (~-soft) ─────────────────────────────────────────────────
    l5: bool | None = None
    if cum_ncp is not None and flow_durability_val is not None:
        l5 = cum_ncp > 0 and flow_durability_val >= durability_min
    elif cum_ncp is not None:
        l5 = cum_ncp > 0

    # ── L6: upturn_organ ──────────────────────────────────────────────────────
    l6: bool | None = None
    if mtf_upturn_state is not None:
        l6 = mtf_upturn_state in ("UPTURN_WATCH", "UPTURN_CONFIRMED")

    # ── L7: leader_quality ────────────────────────────────────────────────────
    l7: bool | None = None
    if failed_breakout_trap is not None:
        l7 = not failed_breakout_trap

    return ConfluenceLegs(
        L1_washout_recent=l1,
        L2_reclaim=l2,
        L3_rvol_elevated=l3,
        L4_vol_durable=l4,
        L5_flow_bid=l5,
        L6_upturn_organ=l6,
        L7_leader_quality=l7,
    )


# ── 9. Washout context (derived from daily bars) ──────────────────────────────

def washout_context(
    bars: pd.DataFrame,
    lookback: int = 90,
) -> dict:
    """Compute washout context fields from a daily-bars DataFrame.

    Reuses ``engine.bollinger_event_signals.bb_lower_reclaim`` for the band
    event; computes trailing 21-session max drawdown from ``close``.

    Args:
        bars: Daily-bars DataFrame with columns ``high``, ``low``, ``close``
            (and optionally ``open``, ``volume``); must be date-ordered
            ascending.  The index may be a DatetimeIndex or any ordinal index.
        lookback: Maximum number of trailing sessions to search for a
            bb_lower_reclaim event (default 90, matching the caller's tail).

    Returns:
        Dict with keys:
          - ``bb_lower_reclaim_days`` (int | None): sessions since the most
            recent bb_lower_reclaim event within the lookback window; None
            when the event never fired in the window.
          - ``drawdown_21d_pct`` (float | None): trailing 21-session max
            drawdown = min over the last 21 sessions of
            (close / rolling-peak-close - 1), a negative float.  None when
            fewer than 2 sessions are available.
          - ``recovery_begun`` (bool | None): True when the most recent
            close is above the close at the 21-session drawdown trough.
            None when drawdown cannot be computed.

    Defensive: returns all-None dict on empty/short/missing-column input.
    """
    null_result: dict = {
        "bb_lower_reclaim_days": None,
        "drawdown_21d_pct": None,
        "recovery_begun": None,
    }

    if bars is None or bars.empty:
        return null_result

    required = {"close", "high", "low"}
    if not required.issubset(bars.columns):
        log.debug("washout_context: missing required columns (need high/low/close)")
        return null_result

    # Work on a tail of `lookback` sessions to keep compute cheap.
    df = bars.tail(lookback).copy()
    if len(df) < 2:
        return null_result

    result: dict = {
        "bb_lower_reclaim_days": None,
        "drawdown_21d_pct": None,
        "recovery_begun": None,
    }

    # ── bb_lower_reclaim_days ─────────────────────────────────────────────────
    try:
        fired = _bes.bb_lower_reclaim(df)
        # fired is a Series of {0.0, 1.0}; find the last 1.0 position.
        fire_positions = [i for i, v in enumerate(fired.values) if v == 1.0]
        if fire_positions:
            last_fire_pos = fire_positions[-1]
            # Sessions since the fire = (len - 1) - last_fire_pos
            sessions_since = (len(df) - 1) - last_fire_pos
            result["bb_lower_reclaim_days"] = int(sessions_since)
    except Exception as e:  # noqa: BLE001
        log.debug("washout_context: bb_lower_reclaim computation failed: %s", e)

    # ── drawdown_21d_pct + recovery_begun ─────────────────────────────────────
    try:
        close = df["close"].astype(float)
        window_21 = close.tail(21)
        if len(window_21) >= 2:
            rolling_peak = window_21.cummax()
            drawdown_series = window_21 / rolling_peak - 1.0
            min_dd = float(drawdown_series.min())
            result["drawdown_21d_pct"] = round(min_dd, 4)

            # recovery_begun: latest close > close at drawdown trough
            trough_idx = int(drawdown_series.values.argmin())
            trough_close = float(window_21.iloc[trough_idx])
            latest_close = float(window_21.iloc[-1])
            result["recovery_begun"] = bool(latest_close > trough_close)
    except Exception as e:  # noqa: BLE001
        log.debug("washout_context: drawdown computation failed: %s", e)

    return result
