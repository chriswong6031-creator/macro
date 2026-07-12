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


# ── 9. Dealer context (from site/gex/<T>.json summary block) ─────────────────

def _g(d: dict, *path):
    """Safe nested get — returns None on any missing key or non-dict intermediate."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _clean(v):
    """Map NaN/inf to None; pass through all other values unchanged."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    import math
    if math.isnan(f) or math.isinf(f):
        return None
    return v


def dealer_context(gex_summary: dict | None) -> dict | None:
    """Normalize a gex/<T>.json summary block into the flat dealer display-context dict.

    Reads the ``summary`` sub-block plus sibling top-level blocks
    (``expected_move``, ``vol_hole``, ``tilt``, ``opex_days``) passed in via
    the same dict when the caller has merged them in advance.

    Args:
        gex_summary: The ``summary`` dict from a ``site/gex/<T>.json`` file,
            optionally augmented with sibling top-level keys (``expected_move``,
            ``vol_hole``, ``tilt``, ``opex_days``).  None → None.

    Returns:
        Flat dict with exactly the 31 keys enumerated in the v2 ruling §4, or
        None when ``gex_summary`` is None.  Any missing sub-field is None.
        NaN/inf values are mapped to None.  Never raises.
    """
    if gex_summary is None:
        return None

    d = gex_summary  # alias for brevity

    try:
        result: dict = {
            # Regime + caveat
            "regime":                   _clean(_g(d, "regime")),
            "structurally_constant":    _clean(_g(d, "regime_passport", "structurally_constant")),
            # GEX surface
            "net_gex_bn":               _clean(_g(d, "net_gex_bn")),
            "gamma_flip":               _clean(_g(d, "gamma_flip")),
            "dist_to_flip_pct":         _clean(_g(d, "dist_to_flip_pct")),
            "call_wall":                _clean(_g(d, "call_wall")),
            "put_wall":                 _clean(_g(d, "put_wall")),
            "call_wall_band":           _clean(_g(d, "call_wall_band")),
            "call_wall_hard":           _clean(_g(d, "call_wall_hard")),
            "call_wall_dist_sigma":     _clean(_g(d, "call_wall_dist_sigma")),
            "put_wall_band":            _clean(_g(d, "put_wall_band")),
            "magnet_up":                _clean(_g(d, "magnet_up")),
            "magnet_down":              _clean(_g(d, "magnet_down")),
            "max_pain":                 _clean(_g(d, "max_pain")),
            # Expected move (may live as sibling top-level or inside summary)
            "expected_move_daily_pct":  _clean(_g(d, "expected_move", "daily_pct")),
            "expected_move_weekly_pct": _clean(_g(d, "expected_move", "weekly_pct")),
            # Vol hole
            "vol_hole_state":           _clean(_g(d, "vol_hole", "state")),
            "vol_hole_bias":            _clean(_g(d, "vol_hole", "bias")),
            "vol_hole_upper":           _clean(_g(d, "vol_hole", "upper")),
            "vol_hole_lower":           _clean(_g(d, "vol_hole", "lower")),
            "vol_hole_compression":     _clean(_g(d, "vol_hole", "compression")),
            # Skew
            "skew_tone":                _clean(_g(d, "skew", "tone")),
            "skew_rr25":                _clean(_g(d, "skew", "rr25")),
            # IV
            "iv30":                     _clean(_g(d, "iv30")),
            "iv_rank_band":             _clean(_g(d, "iv_rank", "band")),
            "iv_rank_pct":              _clean(_g(d, "iv_rank", "rank_pct")),
            "iv_rank_low_confidence":   _clean(_g(d, "iv_rank", "low_confidence")),
            # OPEX + tier
            "opex_days":                _clean(_g(d, "opex_days")),
            "tier":                     _clean(_g(d, "tier")),
            "top_oi_share":             _clean(_g(d, "top_oi_share")),
            # Tilt
            "tilt_read":                _clean(_g(d, "tilt", "read")),
        }
    except Exception:  # noqa: BLE001
        return None

    return result


# ── 10. Stance derivation ─────────────────────────────────────────────────────

# Stance key → (EN copy, ZH copy, lane key)
_STANCE_COPY: dict[str, tuple[str, str, str]] = {
    "take_profits": (
        "Take profits — stretched into the call wall / pin; expect mean-reversion, don't chase.",
        "止盈 — 已拉伸至认购墙/到期钉住区域；预期均值回归，不追涨。",
        "take_profits",
    ),
    "act": (
        "Buy now — washout reclaimed on durable volume; structure supports continuation. "
        "Stop below the base.",
        "立即买入 — 洗盘后在持续成交量中收复，结构支持延续。止损设在底部结构下方。",
        "act",
    ),
    "get_ready": (
        "Almost ready — washout base built; waiting for a reclaim above VWAP on volume.",
        "即将就绪 — 洗盘底部已形成；等待放量收复VWAP。",
        "get_ready",
    ),
    "in_favour": (
        "In favour — trending above VWAP; ride it, no fresh entry here.",
        "顺势而行 — 强势运行于VWAP上方；持仓，不追新入场。",
        "in_favour",
    ),
    "watch": (
        "Watch — don't chase — moving without a washout base (or trap-prone); "
        "wait for structure.",
        "观望 — 不追涨 — 无洗盘底部结构即上涨（或回踩陷阱型）；等待结构形成。",
        "watch",
    ),
    "stand_aside": (
        "Stand aside — quiet tape, no setup.",
        "观望 — 盘面平静，暂无机会。",
        "stand_aside",
    ),
}

# Off-hours get_ready copy (different from live-session copy)
_OFF_HOURS_GET_READY_EN = "Base in place — waiting for the open."
_OFF_HOURS_GET_READY_ZH = "底部已形成 — 等待开盘。"


def stance(
    *,
    legs: "ConfluenceLegs",
    K: int,
    vwap_delta_pct: float | None = None,
    price_up_on_day: bool | None = None,
    squeeze_coiled: bool | None = None,
    dealer: dict | None = None,
    live_present: bool = True,
) -> dict:
    """Derive the stance lane from confluence legs + dealer context.

    Implements the deterministic boolean precedence in v2 ruling §3.
    No weighted scores.  First-match-wins over the 6 lanes.

    Off-hours branch (``live_present=False``): only the nightly skeleton is
    computed — L1 ∧ (L6 ∨ squeeze_coiled) ⇒ ``get_ready``; else ``stand_aside``.

    Args:
        legs: ConfluenceLegs dataclass (L1–L7, computed booleans/None).
        K: Count of True legs (redundant from legs.K but kept for callers that
           pass it explicitly).
        vwap_delta_pct: Spot price % above VWAP (positive = above).  Used by
            ``extended_up``.  None → helper is False.
        price_up_on_day: True when spot > prevClose.  Used for rule 5 (Watch).
            None treated as False for the Watch gate.
        squeeze_coiled: True when the vol-squeeze is in a coiled state.  Used
            in ``get_ready`` rule 3 and off-hours skeleton.
        dealer: Flat dealer-context dict from ``dealer_context()``.  Fields
            used: ``call_wall_hard``, ``call_wall_dist_sigma``,
            ``expected_move_daily_pct``, ``opex_days``, ``regime``.
            None or missing fields → relevant helpers are False.
        live_present: False during off-hours / null tape; triggers the
            nightly-skeleton branch.

    Returns:
        Dict with keys: ``key`` (stance slug), ``en`` (plain EN copy),
        ``zh`` (plain ZH copy), ``lane`` (color/emoji key = stance slug).
    """

    def _dealer(key: str):
        if dealer is None:
            return None
        return dealer.get(key)

    # ── derived helpers ───────────────────────────────────────────────────────

    # extended_up: price stretched vs IV-implied 1σ OR near hard call wall above VWAP
    def _extended_up() -> bool:
        em = _dealer("expected_move_daily_pct")
        cw_hard = _dealer("call_wall_hard")
        cw_sigma = _dealer("call_wall_dist_sigma")
        # arm 1: vwap_delta >= 1.5 × daily expected move
        if vwap_delta_pct is not None and em is not None:
            try:
                if float(vwap_delta_pct) >= 1.5 * float(em):
                    return True
            except (TypeError, ValueError):
                pass
        # arm 2: hard call wall close AND price above VWAP
        if cw_hard and cw_sigma is not None and vwap_delta_pct is not None:
            try:
                if bool(cw_hard) and float(cw_sigma) <= 0.5 and float(vwap_delta_pct) > 0:
                    return True
            except (TypeError, ValueError):
                pass
        return False

    # pin_watch: OPEX close + long-gamma + near wall/magnet
    def _pin_watch() -> bool:
        opex = _dealer("opex_days")
        regime = _dealer("regime")
        cw_sigma = _dealer("call_wall_dist_sigma")
        if opex is None or regime is None:
            return False
        try:
            if int(opex) <= 5 and str(regime).lower() == "long" and cw_sigma is not None:
                return float(cw_sigma) <= 0.01  # ~1% approx
        except (TypeError, ValueError):
            pass
        return False

    # into_ceiling: hard call wall is close
    def _into_ceiling() -> bool:
        cw_hard = _dealer("call_wall_hard")
        cw_sigma = _dealer("call_wall_dist_sigma")
        if cw_hard is None or cw_sigma is None:
            return False
        try:
            return bool(cw_hard) and float(cw_sigma) <= 0.5
        except (TypeError, ValueError):
            return False

    # ── off-hours skeleton ────────────────────────────────────────────────────
    if not live_present:
        l1 = legs.L1_washout_recent is True
        l6 = legs.L6_upturn_organ is True
        sq = squeeze_coiled is True
        if l1 and (l6 or sq):
            return {
                "key": "get_ready",
                "en": _OFF_HOURS_GET_READY_EN,
                "zh": _OFF_HOURS_GET_READY_ZH,
                "lane": "get_ready",
            }
        en, zh, lane = _STANCE_COPY["stand_aside"]
        return {"key": "stand_aside", "en": en, "zh": zh, "lane": lane}

    # ── live-session precedence (first match wins) ────────────────────────────
    l1 = legs.L1_washout_recent is True
    l2 = legs.L2_reclaim is True
    l3 = legs.L3_rvol_elevated is True
    l4 = legs.L4_vol_durable is True
    l5 = legs.L5_flow_bid is True
    l6 = legs.L6_upturn_organ is True
    # Quality gates the good lanes as a NEGATIVE filter: only a KNOWN trap
    # (L7 is False) blocks act/get_ready/in_favour. Unknown quality (None) must
    # NOT block — trap flags are sparse, so `is True` would make "Buy now"
    # unreachable for most leaders. Ruling §3: L7 = "not a known trap".
    l7 = legs.L7_leader_quality is not False
    sq = squeeze_coiled is True
    pup = price_up_on_day is True

    extended_up = _extended_up()
    pin_watch = _pin_watch()
    into_ceiling = _into_ceiling()

    def _make(key: str) -> dict:
        en, zh, lane = _STANCE_COPY[key]
        return {"key": key, "en": en, "zh": zh, "lane": lane}

    # Rule 1 — Take profits: up-move stretched into resistance
    # Price above VWAP AND (extended_up OR pin_watch)
    above_vwap = (vwap_delta_pct is not None and vwap_delta_pct > 0) or l2
    if above_vwap and (extended_up or pin_watch):
        return _make("take_profits")

    # Rule 2 — Buy now (act): full continuation, not into a ceiling
    # L1 ∧ L2 ∧ L4 ∧ L7 ∧ (L3 ∨ L5) ∧ NOT into_ceiling
    if l1 and l2 and l4 and l7 and (l3 or l5) and not into_ceiling:
        return _make("act")

    # Rule 3 — Almost ready (get_ready): base in place, trigger not fired
    # L1 ∧ (L6 ∨ squeeze_coiled) ∧ L7 ∧ NOT L2
    if l1 and (l6 or sq) and l7 and not l2:
        return _make("get_ready")

    # Rule 4 — In favour: trending and holding, no fresh washout
    # L2 ∧ L6 ∧ (L3 ∨ L4) ∧ L7 ∧ NOT L1
    if l2 and l6 and (l3 or l4) and l7 and not l1:
        return _make("in_favour")

    # Rule 5 — Watch: active without structure, or trap-prone
    # (L3 ∨ price_up_on_day) AND (NOT L1 OR L7 == false)
    l7_false = legs.L7_leader_quality is False
    if (l3 or pup) and (not l1 or l7_false):
        return _make("watch")

    # Rule 6 — Stand aside (default)
    return _make("stand_aside")


# ── 11. Washout context (derived from daily bars) ─────────────────────────────

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
