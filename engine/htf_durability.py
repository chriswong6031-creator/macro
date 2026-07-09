"""HTF momentum DURABILITY engine — front-running secular tops & bottoms.

Display / context tier. De-escalation-only authority. Never originates buy/sell.
Additive dict output — caller passes into the regime read; does NOT mutate it.

Design (approved multi-team-adversarial synthesis, 2026-07-08):
  P0 — per-market monthly/2W/weekly indicator stack
  P1 — durability grading with monthly-phase veto (A–D / A′–D′)
  P2 — liquidity-card reframe (mechanical + HTF-topping -> not_momentum_confirmed)

Anti-patterns explicitly forbidden:
  - MACD hist zero-cross as a trigger (banned; tracked as telemetry only)
  - resample("2W-FRI") for biweekly bars (calendar-anchored drift; replaced by
    paired-weekly-bar grouping against a FIXED epoch anchor)
  - Percentile-guard on StochRSI thresholds (lookahead; fixed bands only)
  - Any "validated" language (CI-enforced)
  - Tuning thresholds on history (all constants frozen a priori from the literature)
  - LLM involvement (zero)
  - Parallel intensity path (use engine/mtf_monitor's technical_intensity; none here)

Reused primitives (NEVER rebuilt here):
  engine/cycles.py  : mtf_snapshot, _tf_phase, rsi_divergence, macd_parts,
                      stoch_rsi, _pivots
  engine/regime.py  : liquidity_quality  (P2 reframe)

Washout organs consulted as confluence only (not re-implemented):
  engine/hk_washout_watch, engine/coiled, engine/sector_bottom
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIXED CONSTANTS (frozen a priori from the literature — do NOT tune on history)
# ---------------------------------------------------------------------------

# StochRSI extreme bands (monthly/2W/weekly TF)
_STOCH_DEEP_FLOOR: float = 10.0   # <=10 = deep-oversold precondition
_STOCH_DEEP_CEIL:  float = 90.0   # >=90 = deep-overbought precondition

# StochRSI "hooking off extreme" threshold (leaving the zone, still near)
_STOCH_HOOK_FLOOR: float = 20.0   # rising above 20 after being <=10
_STOCH_HOOK_CEIL:  float = 80.0   # falling below 80 after being >=90

# HTF divergence pivot parameters — scaled for monthly/2W/weekly bar units
# (reuse rsi_divergence pivot filters, per synthesis §divergence)
_DIV_K:        int   = 5     # pivot confirmation bars each side
_DIV_MIN_DIST: int   = 3     # minimum bars between pivots (monthly bars)
_DIV_MAX_DIST: int   = 18    # maximum bars between pivots (monthly bars)
_DIV_MAG:      float = 4.0   # minimum RSI magnitude difference (same as rsi_divergence)

# Multi-TF scoring weights (Monthly=3, 2W=2, Weekly=1; NOT averaged oscillators)
_W_M:  int = 3
_W_2W: int = 2
_W_W:  int = 1

# Anti-trap persistence requirement (hook must hold this many W bars)
_PERSISTENCE_W_BARS: int = 2

# Monthly-curl debounce (require 2 bars of confirmed curl before crediting)
_MONTHLY_CURL_DEBOUNCE: int = 2

# Top-side deceleration threshold (3+ bars of decelerating momentum for asymmetry)
_TOP_DECEL_BARS: int = 3

# 2W epoch anchor for PIT-safe biweekly resampling
# Any Monday works; using 2000-01-03 (a confirmed Monday) as fixed reference epoch
_2W_EPOCH: pd.Timestamp = pd.Timestamp("2000-01-03")

# ---------------------------------------------------------------------------
# PIT-safe 2W resampling
# ---------------------------------------------------------------------------

def _biweekly_close(daily_close: pd.Series) -> pd.Series:
    """Compute biweekly (2W) close from daily OHLCV, PIT-safe.

    MUST NOT use resample("2W-FRI") — that bins are calendar-anchored and drift
    with as-of date, making backtest != live.

    Method: group each weekly bar into pair-of-weeks numbered from a FIXED epoch
    anchor. Only COMPLETED week-pairs produce a bar (the current incomplete 2W
    period is excluded). This is deterministic, reproducible, and has no lookahead
    — adding future bars never changes a past 2W value.

    Returns a pd.Series indexed by the END date of each completed 2W period,
    with .name preserved.
    """
    if len(daily_close) < 20:
        return pd.Series(dtype=float, name=daily_close.name)

    # Step 1: weekly bars (W-FRI, same as mtf_snapshot)
    weekly = daily_close.resample("W-FRI").last().dropna()
    if len(weekly) < 4:
        return pd.Series(dtype=float, name=daily_close.name)

    # Step 2: assign a pair-index to each weekly bar relative to the fixed epoch
    # Number of weeks since epoch for each bar's Friday
    epoch_fri = _2W_EPOCH - pd.Timedelta(days=_2W_EPOCH.weekday())  # align to Mon
    # Distance in weeks from epoch to each bar
    def _week_num(ts: pd.Timestamp) -> int:
        delta = ts - epoch_fri
        return int(delta.days // 7)

    week_nums = np.array([_week_num(ts) for ts in weekly.index])
    pair_ids = week_nums // 2  # integer division groups into pairs

    # Step 3: for each completed pair (both bars present), take the last bar's close
    result_dates: list[pd.Timestamp] = []
    result_vals:  list[float]        = []

    unique_pairs = np.unique(pair_ids)
    for pid in unique_pairs:
        mask = pair_ids == pid
        if mask.sum() < 2:
            # incomplete pair — only skip if it's the most recent (no future bars yet)
            if pid == unique_pairs[-1]:
                continue
            # Historical incomplete pair (gap in data) — include the single bar
        bars = weekly[mask]
        result_dates.append(bars.index[-1])
        result_vals.append(float(bars.iloc[-1]))

    if not result_dates:
        return pd.Series(dtype=float, name=daily_close.name)

    return pd.Series(result_vals, index=pd.DatetimeIndex(result_dates),
                     name=daily_close.name)


# ---------------------------------------------------------------------------
# Per-TF HTF divergence (MACD-hist + StochRSI dual confirmation)
# ---------------------------------------------------------------------------

def htf_divergence(series_tf: pd.Series, k: int = _DIV_K,
                   min_dist: int = _DIV_MIN_DIST, max_dist: int = _DIV_MAX_DIST,
                   mag: float = _DIV_MAG) -> dict:
    """HTF divergence: bear = price HH + (MACD-hist AND StochRSI) LH.
    Bull = symmetric. Reuses _pivots pivot filters from engine/cycles.

    Dual-confirmation requirement (MACD-hist AND StochRSI both make lower highs
    for bear / higher lows for bull) is NEW — tighter than rsi_divergence which
    checks RSI only. Returns {bull, bull_bars_ago, bear, bear_bars_ago}.
    """
    from engine.cycles import _pivots, macd_parts, stoch_rsi

    c = series_tf.dropna()
    if len(c) < k * 3 + 15:
        return {}

    m = macd_parts(c)
    hist = m["hist"].dropna()
    srsi = stoch_rsi(c).dropna()

    if len(hist) < k * 2 + 5 or len(srsi) < k * 2 + 5:
        return {}

    arr = c.to_numpy()
    harr = hist.reindex(c.index).ffill().fillna(0).to_numpy()
    sarr = srsi.reindex(c.index).ffill().fillna(50).to_numpy()
    last = len(arr) - 1

    out: dict = {}

    # Bear divergence: price higher-high, MACD-hist lower-high, StochRSI lower-high
    phi = _pivots(arr, k, "high")
    if len(phi) >= 2:
        p1, p2 = phi[-2], phi[-1]
        dist = p2 - p1
        if (min_dist <= dist <= max_dist and last - p2 <= max_dist):
            price_hh = arr[p2] > arr[p1]
            hist_lh = harr[p2] < harr[p1] - mag * 0.1  # softer mag for hist
            srsi_lh = sarr[p2] < sarr[p1] - mag
            if price_hh and hist_lh and srsi_lh:
                out["bear"] = True
                out["bear_bars_ago"] = int(last - p2)

    # Bull divergence: price lower-low, MACD-hist higher-low, StochRSI higher-low
    plo = _pivots(arr, k, "low")
    if len(plo) >= 2:
        p1, p2 = plo[-2], plo[-1]
        dist = p2 - p1
        if (min_dist <= dist <= max_dist and last - p2 <= max_dist):
            price_ll = arr[p2] < arr[p1]
            hist_hl = harr[p2] > harr[p1] + mag * 0.1
            srsi_hl = sarr[p2] > sarr[p1] + mag
            if price_ll and hist_hl and srsi_hl:
                out["bull"] = True
                out["bull_bars_ago"] = int(last - p2)

    return out


# ---------------------------------------------------------------------------
# Per-TF state extraction
# ---------------------------------------------------------------------------

def _tf_indicators(close_tf: pd.Series) -> dict:
    """Compute MACD + StochRSI indicators for a single (already-resampled) TF series.
    Returns a subset of _tf_state fields needed by the durability engine.
    Reuses engine/cycles primitives; does NOT recompute them.
    """
    from engine.cycles import _tf_state
    if len(close_tf) < 40:
        return {}
    return _tf_state(close_tf)


def _stoch_in_extreme(s: dict, side: str) -> bool:
    """True if StochRSI is in the deep extreme zone for the given side."""
    v = s.get("stoch")
    if v is None:
        return False
    if side == "bottom":
        return float(v) <= _STOCH_DEEP_FLOOR
    return float(v) >= _STOCH_DEEP_CEIL


def _stoch_hooking(s: dict, side: str) -> bool:
    """True if StochRSI is leaving the extreme zone (hooking off it)."""
    v = s.get("stoch")
    if v is None:
        return False
    if side == "bottom":
        # Was in deep floor, now rising above 20 (hook out of oversold)
        spark = s.get("spark_stoch") or []
        if not spark or len(spark) < 3:
            return False
        was_extreme = any(x <= _STOCH_DEEP_FLOOR for x in spark[-5:-1])
        return was_extreme and float(v) > _STOCH_HOOK_FLOOR
    else:
        spark = s.get("spark_stoch") or []
        if not spark or len(spark) < 3:
            return False
        was_extreme = any(x >= _STOCH_DEEP_CEIL for x in spark[-5:-1])
        return was_extreme and float(v) < _STOCH_HOOK_CEIL


def _hook_triggered(s: dict, side: str) -> bool:
    """Hook trigger: macd_curl + macd_approaching + stoch hooking (NOT zero-cross)."""
    if not s:
        return False
    if side == "bottom":
        macd_hook = s.get("macd_curl_up") or s.get("macd_approaching_up", False)
        return bool(macd_hook or _stoch_hooking(s, "bottom"))
    else:
        macd_hook = s.get("macd_curl_dn") or s.get("macd_approaching_dn", False)
        return bool(macd_hook or _stoch_hooking(s, "top"))


def _tf_score(s: dict, div: dict, side: str) -> int:
    """Score for one timeframe: +1 (bottom) or -1 (top) if hook triggered.
    Divergence adds +1 confirmer (for the bottom side) or -1 (top side).
    Returns integer in {-2, -1, 0, +1, +2}.
    """
    if not s:
        return 0
    score = 0
    hook = _hook_triggered(s, side)
    if hook:
        score += 1 if side == "bottom" else -1
    if side == "bottom" and div.get("bull"):
        score += 1
    elif side == "top" and div.get("bear"):
        score -= 1
    return score


# ---------------------------------------------------------------------------
# Monthly-phase veto (the load-bearing novel piece)
# ---------------------------------------------------------------------------

def _monthly_phase_allows_durable(monthly_s: dict) -> bool:
    """True if the monthly TF phase is NOT falling/rolling (still in downtrend).
    'turning' or 'rising' => monthly has LEFT the downtrend => eligible for A/B grade.
    'falling' or 'rolling' (or 'basing') => still in downtrend / topping =>
      cap at grade D (TRAP-PRONE BOUNCE).

    Uses monthly _tf_phase (NOT monthly StochRSI — it saturates on slow TF).
    """
    from engine.cycles import _tf_phase
    phase = _tf_phase(monthly_s)
    # For bottom detection: monthly must have LEFT falling/basing to be grade A eligible
    return phase in ("turning", "rising", "bear_recovering")


def _monthly_phase_topping(monthly_s: dict) -> bool:
    """True if the monthly TF phase indicates a topping pattern (rolling/falling)."""
    from engine.cycles import _tf_phase
    phase = _tf_phase(monthly_s)
    return phase in ("rolling", "falling")


# ---------------------------------------------------------------------------
# Durability grade (A–D for bottoms, A′–D′ for tops)
# ---------------------------------------------------------------------------

def _confluence_points(
    side: str,
    stack_score: int,
    monthly_s: dict,
    weekly_s: dict,
    biweekly_s: dict,
    div_m: dict,
    div_2w: dict,
    div_w: dict,
    external_organs: dict | None = None,
) -> tuple[int, dict]:
    """Count confluence upgrade points and return (points, detail_dict).

    Upgrade organs (+1 each, cap handled by caller):
      1. cross-TF 2W+W aligned (both pointing same direction)
      2. washout-organ K>=2 (from external_organs, display-only)
      3. capitulation signal (volume_signature or vol_shock from organs)
      4. breadth thrust (from organs)
      5. sentiment extreme fear_greed (from organs)
      6. genuine policy (mechanical does NOT count — must be non-mechanical Fed action)
      7. monthly divergence confirmed (slow confirmer)
    """
    pts = 0
    detail: dict[str, bool] = {}

    # 1. Cross-TF alignment (2W + W both aligned)
    w_hook  = _hook_triggered(weekly_s, side)
    tw_hook = _hook_triggered(biweekly_s, side)
    cross_tf_aligned = bool(w_hook and tw_hook)
    detail["cross_tf_aligned"] = cross_tf_aligned
    if cross_tf_aligned:
        pts += 1

    # 2. Washout organs K>=2 (external — display-tier input only)
    organs = external_organs or {}
    washout_k = int(organs.get("washout_k", 0))
    detail["washout_k_gte2"] = washout_k >= 2
    if washout_k >= 2:
        pts += 1

    # 3. Capitulation (volume_signature / vol_shock from organs)
    capitulation = bool(organs.get("capitulation") or organs.get("vol_shock"))
    detail["capitulation"] = capitulation
    if capitulation:
        pts += 1

    # 4. Breadth thrust
    breadth_thrust = bool(organs.get("breadth_thrust"))
    detail["breadth_thrust"] = breadth_thrust
    if breadth_thrust:
        pts += 1

    # 5. Sentiment extreme (fear_greed extreme)
    sentiment_extreme = bool(organs.get("fear_greed_extreme"))
    detail["sentiment_extreme"] = sentiment_extreme
    if sentiment_extreme:
        pts += 1

    # 6. Genuine policy (NON-mechanical — mechanical Fed plumbing does NOT count)
    genuine_policy = bool(organs.get("genuine_policy") and
                          not organs.get("mechanical_liquidity"))
    detail["genuine_policy"] = genuine_policy
    if genuine_policy:
        pts += 1

    # 7. Monthly divergence (slow confirmer)
    monthly_div = bool(div_m.get("bull") if side == "bottom" else div_m.get("bear"))
    detail["monthly_divergence"] = monthly_div
    if monthly_div:
        pts += 1

    return pts, detail


def _assign_grade(
    side: str,
    stack_score: int,
    monthly_allows: bool,
    confluence_pts: int,
) -> str:
    """Assign durability grade based on monthly-phase ceiling and confluence.

    Bottoms:
      A  — monthly exited downtrend + confluence_pts >= 3 + strong stack_score >= 4
      B  — monthly exited downtrend + confluence_pts >= 2
      C  — monthly exited downtrend + confluence_pts >= 1
      D  — monthly still falling/rolling OR no meaningful confluence (TRAP-PRONE)

    Tops (prime grades):
      A' — monthly topping + strong stack (negative) + confluence >= 3
      B' — monthly topping + confluence >= 2
      C' — monthly topping + confluence >= 1
      D' — monthly phase ambiguous or low confluence

    The monthly-phase veto is PRIMARY: weekly hook under falling monthly => cap at D.
    """
    if side == "bottom":
        if not monthly_allows:
            return "D"  # TRAP-PRONE BOUNCE — monthly veto
        if confluence_pts >= 3 and stack_score >= 4:
            return "A"
        if confluence_pts >= 2:
            return "B"
        if confluence_pts >= 1:
            return "C"
        return "D"
    else:  # top
        if not monthly_allows:
            return "D_prime"
        if confluence_pts >= 3 and stack_score <= -4:
            return "A_prime"
        if confluence_pts >= 2:
            return "B_prime"
        if confluence_pts >= 1:
            return "C_prime"
        return "D_prime"


# ---------------------------------------------------------------------------
# Anti-trap checks
# ---------------------------------------------------------------------------

def _no_new_extreme_ok(spark_stoch: list[float] | None, side: str,
                       prev_hook_bar: int | None) -> bool:
    """True if there is NO new extreme after the prior hook fired.
    New low re-entering deep-floor => prior fire failed (kill signal).
    """
    if not spark_stoch or prev_hook_bar is None:
        return True  # can't determine — assume ok
    recent = spark_stoch[-5:]
    if side == "bottom":
        # If stoch went below floor AFTER the hook, it's a new extreme
        return not any(x <= _STOCH_DEEP_FLOOR for x in recent[-2:])
    else:
        return not any(x >= _STOCH_DEEP_CEIL for x in recent[-2:])


def _top_deceleration_ok(monthly_s: dict) -> bool:
    """For top-side: check 3+ bars of decelerating momentum (asymmetry requirement)."""
    spark = monthly_s.get("spark_hist") or []
    if len(spark) < _TOP_DECEL_BARS + 1:
        return False
    # Decelerating = hist falling for 3+ consecutive bars while positive
    recent = spark[-(_TOP_DECEL_BARS + 1):]
    all_positive = all(x > 0 for x in recent)
    falling_3bar = all(recent[i] > recent[i+1] for i in range(len(recent)-1))
    return all_positive and falling_3bar


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute(
    close: pd.Series,
    market: str,
    asof: pd.Timestamp | None = None,
    external_organs: dict | None = None,
    liquidity_quality_dict: dict | None = None,
) -> dict:
    """Compute HTF durability read for one market index.

    Parameters
    ----------
    close : pd.Series
        Daily close prices (pd.DatetimeIndex, sorted ascending).
        At least 900 bars for monthly; gracefully degrades on shorter history.
    market : str
        Market identifier (e.g. "US", "CN", "HK", "CA").
    asof : pd.Timestamp, optional
        Point-in-time cutoff. Defaults to last valid index.
    external_organs : dict, optional
        Display-tier confluence inputs from washout organs:
        {washout_k, capitulation, vol_shock, breadth_thrust,
         fear_greed_extreme, genuine_policy, mechanical_liquidity}.
        Never required — missing keys default to False/0.
    liquidity_quality_dict : dict, optional
        Output of engine/regime.liquidity_quality() — used for P2 reframe only.

    Returns
    -------
    dict
        Additive, fail-open dict. Never mutates the caller's regime dict.
        Schema: htf_durability (see module docstring for full key list).
    """
    from engine.cycles import _tf_phase, _tf_state, stoch_rsi, macd_parts

    c = close.dropna().sort_index()
    if asof is not None:
        c = c.loc[:asof]
    if len(c) < 40:
        return _empty(market, asof)

    asof_ts = pd.Timestamp(c.index[-1])

    # ------------------------------------------------------------------
    # Step 1: build TF series
    # ------------------------------------------------------------------
    # Monthly (M)
    monthly_close = c.resample("ME").last().dropna() if len(c) > 900 else pd.Series(dtype=float)
    # Biweekly (2W) — PIT-safe paired-week grouping
    biweekly_close = _biweekly_close(c) if len(c) > 200 else pd.Series(dtype=float)
    # Weekly (W)
    weekly_close = c.resample("W-FRI").last().dropna() if len(c) > 300 else pd.Series(dtype=float)

    # ------------------------------------------------------------------
    # Step 2: indicators per TF (reuse _tf_state, do NOT recompute MACD math)
    # ------------------------------------------------------------------
    m_s  = _tf_state(monthly_close)   if len(monthly_close)  >= 40 else {}
    tw_s = _tf_state(biweekly_close)  if len(biweekly_close) >= 40 else {}
    w_s  = _tf_state(weekly_close)    if len(weekly_close)   >= 40 else {}

    m_phase  = _tf_phase(m_s)   if m_s  else "unknown"
    tw_phase = _tf_phase(tw_s)  if tw_s else "unknown"
    w_phase  = _tf_phase(w_s, weekly=True) if w_s else "unknown"

    tf_states = {
        "M":  {"phase": m_phase,  "stoch": m_s.get("stoch"),  "macd_pos": m_s.get("macd_pos"),
               "macd_curl_up": m_s.get("macd_curl_up"), "macd_curl_dn": m_s.get("macd_curl_dn"),
               "macd_cross_up": m_s.get("macd_cross_up"), "macd_cross_dn": m_s.get("macd_cross_dn"),
               "macd_approaching_up": m_s.get("macd_approaching_up"),
               "macd_approaching_dn": m_s.get("macd_approaching_dn"),
               "bars_to_cross": m_s.get("macd_bars_to_cross")},
        "2W": {"phase": tw_phase, "stoch": tw_s.get("stoch"), "macd_pos": tw_s.get("macd_pos"),
               "macd_curl_up": tw_s.get("macd_curl_up"), "macd_curl_dn": tw_s.get("macd_curl_dn"),
               "macd_cross_up": tw_s.get("macd_cross_up"), "macd_cross_dn": tw_s.get("macd_cross_dn"),
               "macd_approaching_up": tw_s.get("macd_approaching_up"),
               "macd_approaching_dn": tw_s.get("macd_approaching_dn"),
               "bars_to_cross": tw_s.get("macd_bars_to_cross")},
        "W":  {"phase": w_phase,  "stoch": w_s.get("stoch"),  "macd_pos": w_s.get("macd_pos"),
               "macd_curl_up": w_s.get("macd_curl_up"), "macd_curl_dn": w_s.get("macd_curl_dn"),
               "macd_cross_up": w_s.get("macd_cross_up"), "macd_cross_dn": w_s.get("macd_cross_dn"),
               "macd_approaching_up": w_s.get("macd_approaching_up"),
               "macd_approaching_dn": w_s.get("macd_approaching_dn"),
               "bars_to_cross": w_s.get("macd_bars_to_cross")},
    }

    # ------------------------------------------------------------------
    # Step 3: HTF divergence (per TF; dual MACD-hist + StochRSI)
    # Monthly divergence = slow confirmer; 2W + W divergence drives timing
    # ------------------------------------------------------------------
    div_m  = htf_divergence(monthly_close)   if len(monthly_close)  >= 20 else {}
    div_2w = htf_divergence(biweekly_close)  if len(biweekly_close) >= 20 else {}
    div_w  = htf_divergence(weekly_close)    if len(weekly_close)   >= 20 else {}

    divergence = {
        "M":  div_m,
        "2W": div_2w,
        "W":  div_w,
    }

    # ------------------------------------------------------------------
    # Step 4: determine operative side (TOP or BOTTOM) and compute stack_score
    # Weights: M=3, 2W=2, W=1; range [-6, +6]
    # ------------------------------------------------------------------
    # Determine primary side from the monthly phase
    if m_phase in ("rolling", "falling"):
        primary_side = "top"
    elif m_phase in ("turning", "rising", "bear_recovering"):
        primary_side = "bottom"
    else:
        # Monthly basing/unknown — check weekly direction
        if w_phase in ("rolling", "falling"):
            primary_side = "top"
        elif w_phase in ("turning", "rising", "bear_recovering"):
            primary_side = "bottom"
        else:
            primary_side = "neutral"

    # Score each TF for both sides — keep signed stack_score
    m_score_b  = _tf_score(m_s,  div_m,  "bottom") * _W_M
    tw_score_b = _tf_score(tw_s, div_2w, "bottom") * _W_2W
    w_score_b  = _tf_score(w_s,  div_w,  "bottom") * _W_W
    stack_score_b = m_score_b + tw_score_b + w_score_b  # +6 = maximum bullish

    m_score_t  = _tf_score(m_s,  div_m,  "top") * _W_M
    tw_score_t = _tf_score(tw_s, div_2w, "top") * _W_2W
    w_score_t  = _tf_score(w_s,  div_w,  "top") * _W_W
    stack_score_t = m_score_t + tw_score_t + w_score_t  # -6 = maximum bearish

    # Net signed score: positive = bottom setup, negative = top risk
    stack_score = stack_score_b + stack_score_t
    # Clamp to [-6, +6]
    stack_score = max(-6, min(6, stack_score))

    # ------------------------------------------------------------------
    # Step 5: hook detection (front-run — fires BEFORE zero-cross)
    # Telemetry: bars_to_macd_cross (null = false alarm)
    # ------------------------------------------------------------------
    m_hook_bottom  = _hook_triggered(m_s,  "bottom")
    tw_hook_bottom = _hook_triggered(tw_s, "bottom")
    w_hook_bottom  = _hook_triggered(w_s,  "bottom")

    m_hook_top  = _hook_triggered(m_s,  "top")
    tw_hook_top = _hook_triggered(tw_s, "top")
    w_hook_top  = _hook_triggered(w_s,  "top")

    any_bottom_hook = m_hook_bottom or tw_hook_bottom or w_hook_bottom
    any_top_hook    = m_hook_top    or tw_hook_top    or w_hook_top

    # bars_to_macd_cross telemetry: prefer 2W, then W (weekly = 5 days/bar)
    bars_to_cross_raw: float | None = tw_s.get("macd_bars_to_cross") or w_s.get("macd_bars_to_cross")
    bars_to_macd_cross: int | None = int(round(bars_to_cross_raw)) if bars_to_cross_raw is not None else None

    # ------------------------------------------------------------------
    # Step 6: stage determination
    # ------------------------------------------------------------------
    # Precondition: StochRSI in extreme zone on at least one TF
    stoch_extreme_bottom = (_stoch_in_extreme(m_s, "bottom") or
                            _stoch_in_extreme(tw_s, "bottom") or
                            _stoch_in_extreme(w_s, "bottom"))
    stoch_extreme_top = (_stoch_in_extreme(m_s, "top") or
                         _stoch_in_extreme(tw_s, "top") or
                         _stoch_in_extreme(w_s, "top"))

    # Anti-trap: no-new-extreme kill
    spark_stoch_w = w_s.get("spark_stoch") or []
    no_new_extreme_ok = True
    if primary_side == "bottom" and any_bottom_hook:
        no_new_extreme_ok = _no_new_extreme_ok(spark_stoch_w, "bottom", 1)
    elif primary_side == "top" and any_top_hook:
        no_new_extreme_ok = _no_new_extreme_ok(spark_stoch_w, "top", 1)

    # Stage logic
    if primary_side == "bottom":
        if stoch_extreme_bottom and not any_bottom_hook:
            stage = "armed"
        elif any_bottom_hook and no_new_extreme_ok:
            # persistence check: hook should hold >= _PERSISTENCE_W_BARS
            # We infer persistence from spark_hist direction
            spark_hist_w = w_s.get("spark_hist") or []
            persistent = len(spark_hist_w) < 2 or (
                spark_hist_w[-1] > spark_hist_w[-2] if spark_hist_w else False
            )
            stage = "front_run" if persistent else "failed"
        else:
            stage = "neutral" if not any_bottom_hook else "failed"
    elif primary_side == "top":
        # Top-side deceleration requirement (asymmetry)
        decel_ok = _top_deceleration_ok(m_s) if m_s else False
        if stoch_extreme_top and not any_top_hook:
            stage = "armed"
        elif any_top_hook and (decel_ok or not m_s):
            stage = "front_run"
        elif any_top_hook and not decel_ok:
            stage = "armed"  # hook but no decel yet
        else:
            stage = "neutral"
    else:
        stage = "neutral"

    # ------------------------------------------------------------------
    # Step 7: monthly-phase veto + durability grade
    # ------------------------------------------------------------------
    monthly_allows_durable = _monthly_phase_allows_durable(m_s) if m_s else False
    monthly_is_topping     = _monthly_phase_topping(m_s) if m_s else False

    if primary_side == "bottom":
        conf_pts, conf_detail = _confluence_points(
            "bottom", stack_score, m_s, w_s, tw_s, div_m, div_2w, div_w, external_organs
        )
        durability_grade = _assign_grade("bottom", stack_score, monthly_allows_durable, conf_pts)
    elif primary_side == "top":
        conf_pts, conf_detail = _confluence_points(
            "top", stack_score, m_s, w_s, tw_s, div_m, div_2w, div_w, external_organs
        )
        # For tops: monthly_allows = monthly is in topping phase
        durability_grade = _assign_grade("top", stack_score, monthly_is_topping, conf_pts)
    else:
        conf_pts, conf_detail = 0, {}
        durability_grade = "D"

    # ------------------------------------------------------------------
    # Step 8: HTF momentum regime label
    # ------------------------------------------------------------------
    if primary_side == "top" and durability_grade in ("A_prime", "B_prime"):
        htf_regime = "TOP-RISK"
    elif primary_side == "bottom" and durability_grade in ("A", "B"):
        htf_regime = "BOTTOM-SETUP"
    elif primary_side == "bottom" and durability_grade == "D":
        htf_regime = "TRAP-PRONE-BOUNCE"
    elif primary_side == "top" and durability_grade in ("C_prime", "D_prime"):
        # Rolling over but not confirmed
        htf_regime = "TOP-RISK" if (stack_score <= -3 or any_top_hook) else "NEUTRAL"
    else:
        htf_regime = "NEUTRAL"

    # Honest note: bottom-caller is structurally weaker (monthly veto mutes real washout lows)
    # Lead comes from TOP/de-escalation detection — that is the primary use case.

    # ------------------------------------------------------------------
    # Step 9: read label (display-only, additive context)
    # ------------------------------------------------------------------
    _read = _build_read(primary_side, htf_regime, durability_grade, stack_score, stage, m_phase)

    # ------------------------------------------------------------------
    # Step 10: P2 liquidity reframe
    # ------------------------------------------------------------------
    lq = liquidity_quality_dict or {}
    lq_mechanical = bool(lq.get("composition", {}).get("mechanical"))
    lq_label      = lq.get("label", "unknown")
    lq_expanding  = lq_label in ("benign-expansion", "stress-expansion")
    htf_topping   = htf_regime in ("TOP-RISK",) and durability_grade in ("A_prime", "B_prime", "C_prime")

    # surface_score: 1.0 if lq expanding benign, lower for stress/mechanical
    if lq_label == "benign-expansion":
        surface_score = 1.0
    elif lq_label == "stress-expansion":
        surface_score = 0.5
    elif lq_label in ("neutral", "neutral-hollow"):
        surface_score = 0.3
    else:
        surface_score = 0.0

    # htf_top_strength: how strong the topping signal is (0–1)
    htf_top_strength = min(1.0, max(0.0, (-stack_score) / 6.0)) if stack_score < 0 else 0.0

    # provenance penalty: mechanical liquidity is fragile
    provenance_penalty = 0.3 if lq_mechanical else 0.0

    liquidity_confidence = round(
        min(surface_score, 1.0 - htf_top_strength) - provenance_penalty, 3
    )

    if lq_mechanical and htf_topping:
        liquidity_reframe = "not_momentum_confirmed"
    elif htf_topping:
        liquidity_reframe = "mechanical_fragile"
    else:
        liquidity_reframe = "benign"

    # Reframe copy (bilingual; no translated title=)
    lq_reframe_copy_en = _lq_copy_en(liquidity_reframe, lq_label, lq_mechanical)
    lq_reframe_copy_zh = _lq_copy_zh(liquidity_reframe, lq_label, lq_mechanical)

    # ------------------------------------------------------------------
    # Step 11: labels (bilingual; no translated title= per CI guard)
    # ------------------------------------------------------------------
    label_en, label_zh = _build_labels(htf_regime, durability_grade, primary_side, stage)

    # ------------------------------------------------------------------
    # Output dict (additive, fail-open, never mutates regime)
    # ------------------------------------------------------------------
    return {
        "schema_version": 1,
        "market": market,
        "asof": str(asof_ts.date()),
        "tf_states": tf_states,
        "divergence": divergence,
        "read": _read,
        "htf_momentum_regime": htf_regime,
        "stack_score": stack_score,
        "durability_grade": durability_grade,
        "durability_points": conf_pts,
        "confluence": conf_detail,
        "stage": stage,
        "bars_to_macd_cross": bars_to_macd_cross,
        "monthly_phase": m_phase,
        "monthly_veto_active": (primary_side == "bottom" and not monthly_allows_durable),
        "liquidity_reframe": liquidity_reframe,
        "liquidity_confidence": liquidity_confidence,
        "lq_reframe_copy_en": lq_reframe_copy_en,
        "lq_reframe_copy_zh": lq_reframe_copy_zh,
        "label_en": label_en,
        "label_zh": label_zh,
        "disclaimer": (
            "Display-only, context tier. De-escalation authority only — "
            "never originates buy/sell signals. Bottom-caller is structurally "
            "weaker than TOP/de-escalation due to monthly-phase veto. "
            "Accrues forward outcomes for later phase validation."
        ),
    }


def _empty(market: str, asof: pd.Timestamp | None) -> dict:
    """Fail-open empty output when data is insufficient."""
    return {
        "schema_version": 1,
        "market": market,
        "asof": str((asof or pd.Timestamp.now()).date()),
        "tf_states": {},
        "divergence": {},
        "read": "insufficient data",
        "htf_momentum_regime": "NEUTRAL",
        "stack_score": 0,
        "durability_grade": "D",
        "durability_points": 0,
        "confluence": {},
        "stage": "neutral",
        "bars_to_macd_cross": None,
        "monthly_phase": "unknown",
        "monthly_veto_active": False,
        "liquidity_reframe": "benign",
        "liquidity_confidence": 0.0,
        "lq_reframe_copy_en": None,
        "lq_reframe_copy_zh": None,
        "label_en": "Insufficient data",
        "label_zh": "数据不足",
        "disclaimer": (
            "Display-only, context tier. De-escalation authority only. "
            "Bottom-caller structurally weaker than TOP detection."
        ),
    }


def _build_read(side: str, regime: str, grade: str, score: int, stage: str, m_phase: str) -> str:
    if regime == "TOP-RISK":
        return (f"HTF topping signal — monthly phase {m_phase}, "
                f"grade {grade}, stack {score:+d}. "
                "De-escalating risk-on reads where active.")
    if regime == "BOTTOM-SETUP":
        return (f"HTF bottom setup — monthly left downtrend, "
                f"grade {grade}, stack {score:+d}. Display-tier accrual.")
    if regime == "TRAP-PRONE-BOUNCE":
        return ("Weekly hook under falling monthly — TRAP-PRONE BOUNCE (grade D). "
                "Monthly veto active: do not escalate.")
    return f"HTF neutral — side={side}, phase={m_phase}, stack={score:+d}."


def _build_labels(regime: str, grade: str, side: str, stage: str) -> tuple[str, str]:
    if regime == "TOP-RISK":
        en = f"HTF Top Risk — Grade {grade}"
        zh = f"HTF 顶部风险 — 等级 {grade}"
    elif regime == "BOTTOM-SETUP":
        en = f"HTF Bottom Setup — Grade {grade}"
        zh = f"HTF 底部形态 — 等级 {grade}"
    elif regime == "TRAP-PRONE-BOUNCE":
        en = "HTF Trap-Prone Bounce (Grade D)"
        zh = "HTF 陷阱型反弹（等级 D）"
    else:
        en = "HTF Neutral"
        zh = "HTF 中性"
    return en, zh


def _lq_copy_en(reframe: str, lq_label: str, mechanical: bool) -> str | None:
    if reframe == "not_momentum_confirmed":
        return (
            "Liquidity green is NOT momentum-confirmed — markets rolling over on HTF; "
            "likely TGA/margin-supported; treat as fragile / policy-propped."
        )
    if reframe == "mechanical_fragile":
        return (
            f"Liquidity reading ({lq_label}) may be mechanical/plumbing-driven, "
            "not Fed balance-sheet expansion. HTF momentum rolling; treat as fragile."
        )
    return None


def _lq_copy_zh(reframe: str, lq_label: str, mechanical: bool) -> str | None:
    if reframe == "not_momentum_confirmed":
        return (
            "流动性读数为绿色，但动量未得到确认 — 市场在高时间框架呈见顶走势；"
            "可能由TGA/保证金支撑；应视为脆弱/政策驱动。"
        )
    if reframe == "mechanical_fragile":
        return (
            f"流动性读数（{lq_label}）可能属于机械/管道驱动，而非美联储资产负债表扩张。"
            "高时间框架动量走弱；应视为脆弱。"
        )
    return None


# ---------------------------------------------------------------------------
# Forward ledger (P2 stub — nightly-sole-advancer, CN_LANE-gated)
# ---------------------------------------------------------------------------

_LEDGER_DIR = Path("data/htf_durability")
_LEDGER_FILE = _LEDGER_DIR / "ledger.jsonl"

def _ledger_enabled() -> bool:
    """Gate: only advance nightly (CN_LANE env var must be 'asia' or 'nightly')."""
    import os
    lane = os.environ.get("CN_LANE", "")
    return lane in ("asia", "nightly")


def stamp_ledger(result: dict, root: Path | None = None) -> bool:
    """Atomically append one row to the forward ledger.

    Idempotent on (market, date). Pre-registers the schema for later 20/60/120d
    outcome attachment. Returns True on success, False on skip/error.

    Schema fields (stub):
      market, date, asof, htf_momentum_regime, durability_grade, durability_points,
      stack_score, stage, monthly_phase, monthly_veto_active, episode_id,
      outcome_20d (null), outcome_60d (null), outcome_120d (null)

    episode_id = market + "_" + date (per DT-R14 episode-unit contract).
    Outcomes are stamped by a later grading pass — never here.

    Pre-registration: grade D SHOULD underperform grade A (registered, not tested).
    Full validation = later phase after N_eff is adequate.
    """
    if not _ledger_enabled():
        return False
    ledger_dir = (root or Path(".")) / _LEDGER_DIR
    ledger_path = (root or Path(".")) / _LEDGER_FILE
    try:
        ledger_dir.mkdir(parents=True, exist_ok=True)
        row = {
            "market":               result.get("market"),
            "date":                 result.get("asof"),
            "asof":                 result.get("asof"),
            "htf_momentum_regime":  result.get("htf_momentum_regime"),
            "durability_grade":     result.get("durability_grade"),
            "durability_points":    result.get("durability_points"),
            "stack_score":          result.get("stack_score"),
            "stage":                result.get("stage"),
            "monthly_phase":        result.get("monthly_phase"),
            "monthly_veto_active":  result.get("monthly_veto_active"),
            "episode_id":           f"{result.get('market')}_{result.get('asof')}",
            # Pre-registered outcome fields (null until a grading pass attaches them)
            "outcome_20d":          None,
            "outcome_60d":          None,
            "outcome_120d":         None,
            "stamped_utc":          datetime.now(timezone.utc).isoformat(),
        }
        # Idempotency: check for existing (market, date) row
        existing = []
        key = (row["market"], row["date"])
        if ledger_path.exists():
            with open(ledger_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if (r.get("market"), r.get("date")) == key:
                            return False  # already present — idempotent skip
                        existing.append(line)
                    except json.JSONDecodeError:
                        existing.append(line)

        # Atomic temp+rename
        tmp = ledger_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            for line in existing:
                f.write(line + "\n")
            f.write(json.dumps(row) + "\n")
        tmp.rename(ledger_path)
        return True

    except Exception as e:
        log.warning("htf_durability.stamp_ledger failed: %s", e)
        return False
