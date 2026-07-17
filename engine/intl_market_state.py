"""Per-market turn state machine for international equities (ITR W1).

Computes a rich daily state + event log for each configured market from
close-price history alone.  Fully causal (no future data), deterministic,
and fail-open per country.

Public interface (frozen — see research/INTL_TURN_ROTATION_REVAMP.md §4):

    STATES: dict[str, dict]
        Metadata per state key: {en, zh, stance_en, stance_zh, css, urgency}

    market_states(
        closes:  dict[str, pd.Series],
        bench:   pd.Series | None = None,
    ) -> dict[str, dict]

Each returned country dict has exactly these keys (None when unavailable):
    state, state_en, state_zh, stance_en, stance_zh, css, since,
    urgency, ext_raw_pct, ext_pctile, ext_z, mom20_pct, mom5_pct,
    rs20_pct, rsi, rsi_at_high, rsi_divergence, macd_state,
    macd_cross_date, dd_pct, dd_vel_10d, vol_z, above_ma20, above_ma50,
    above_ma200, was_parabolic_40d, peak_date, data_limited, events
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from engine.technicals import rsi as _wilder_rsi

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State catalogue
# ---------------------------------------------------------------------------

STATES: dict[str, dict] = {
    "crash": {
        "en": "Crash in progress",
        "zh": "崩跌进行中",
        "stance_en": "Stand aside — the fall is not over",
        "stance_zh": "观望离场 — 跌势未止",
        "css": "state-crash",
        "urgency": 9,
    },
    "breaking": {
        "en": "Breaking down",
        "zh": "正在破位",
        "stance_en": "Reduce risk now",
        "stance_zh": "立即降低风险",
        "css": "state-breaking",
        "urgency": 8,
    },
    "topping": {
        "en": "Turn risk",
        "zh": "拐点风险",
        "stance_en": "Early breakdown signs — tighten stops",
        "stance_zh": "出现早期破位迹象 — 收紧止损",
        "css": "state-topping",
        "urgency": 7,
    },
    "parabolic": {
        "en": "Parabolic",
        "zh": "抛物线走势",
        "stance_en": "Protect gains — don't chase",
        "stance_zh": "保住利润 — 不要追高",
        "css": "state-parabolic",
        "urgency": 6,
    },
    "extended": {
        "en": "Stretched",
        "zh": "涨幅偏高",
        "stance_en": "Don't add here",
        "stance_zh": "不宜加仓",
        "css": "state-extended",
        "urgency": 5,
    },
    "downtrend": {
        "en": "Downtrend",
        "zh": "下行趋势",
        "stance_en": "Stand aside",
        "stance_zh": "观望",
        "css": "state-downtrend",
        "urgency": 4,
    },
    "recovery": {
        "en": "Repairing",
        "zh": "修复中",
        "stance_en": "Early recovery — no rush to buy",
        "stance_zh": "初步回升 — 不急于买入",
        "css": "state-recovery",
        "urgency": 3,
    },
    "basing": {
        "en": "Trying to bottom",
        "zh": "尝试筑底",
        "stance_en": "Watch — don't catch the knife",
        "stance_zh": "观察 — 不要急于抄底",
        "css": "state-basing",
        "urgency": 2,
    },
    "uptrend": {
        "en": "Healthy trend",
        "zh": "趋势健康",
        "stance_en": "Healthy trend",
        "stance_zh": "趋势健康",
        "css": "state-uptrend",
        "urgency": 1,
    },
    "calm": {
        "en": "Quiet",
        "zh": "平静",
        "stance_en": "Nothing to do",
        "stance_zh": "无需操作",
        "css": "state-calm",
        "urgency": 0,
    },
}

# States that count as "extended-or-parabolic" for the path-memory check
_EXT_OR_PARA_STATES = {"extended", "parabolic"}

# "Lineage" states that qualify for recovery/basing transitions
_DOWNWARD_LINEAGE = {"downtrend", "crash", "basing", "breaking"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        return None if np.isnan(v) or np.isinf(v) else v
    except (TypeError, ValueError):
        return None


def _rolling_percentile_causal(
    s: pd.Series,
    window: int,
    min_periods: int,
) -> pd.Series:
    """For each index i, compute percentile of s[i] vs s[i-window+1 .. i-1].
    Fully causal: today's value is ranked against its own history only.
    Returns 0..100.
    """
    arr = s.to_numpy(dtype=float)
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(n):
        start = max(0, i - window + 1)
        hist = arr[start:i]  # exclude today — rank today vs prior
        if len(hist) < min_periods - 1:
            continue
        valid = hist[np.isfinite(hist)]
        if len(valid) == 0:
            continue
        result[i] = float(np.mean(valid <= arr[i])) * 100.0
    return pd.Series(result, index=s.index)


def _compute_components(close: pd.Series) -> pd.DataFrame:
    """Compute all daily components causally over the full series.

    Returns a DataFrame with one row per trading day containing all
    intermediate and final component fields needed for state resolution.
    """
    px = close.dropna().sort_index()
    if len(px) < 10:
        return pd.DataFrame()

    f = pd.DataFrame(index=px.index)
    f["px"] = px

    # --- MAs ---
    f["sma20"] = px.rolling(20, min_periods=10).mean()
    f["sma50"] = px.rolling(50, min_periods=25).mean()
    f["sma200"] = px.rolling(200, min_periods=100).mean()

    f["above_ma20"] = px > f["sma20"]
    f["above_ma50"] = px > f["sma50"]
    f["above_ma200"] = px > f["sma200"]

    # --- Extension ---
    f["ext_raw"] = (px / f["sma200"] - 1.0) * 100.0  # pct

    # ext_z: z-score of (px/sma200-1) vs trailing 252d own history
    ext_ratio = px / f["sma200"] - 1.0
    ext_mean = ext_ratio.rolling(252, min_periods=120).mean()
    ext_std = ext_ratio.rolling(252, min_periods=120).std().replace(0, np.nan)
    f["ext_z"] = (ext_ratio - ext_mean) / ext_std

    # ext_pctile: causal rank vs trailing 2520 sessions (10y target)
    # Only computed once we have enough; min 756 for data_limited=False
    f["ext_pctile"] = _rolling_percentile_causal(
        ext_ratio, window=2520, min_periods=756
    )
    # data_limited flag: fewer than 756 sessions of ext history
    # We proxy: ext history requires sma200 (200 sessions), so ext starts ~200 bars in.
    # Count non-nan ext_ratio rows up to each point
    ext_ratio_valid = ext_ratio.notna().cumsum()
    f["data_limited"] = ext_ratio_valid < 756

    # --- Momentum ---
    f["mom20_pct"] = px.pct_change(20, fill_method=None) * 100.0
    f["mom5_pct"] = px.pct_change(5, fill_method=None) * 100.0
    f["ret20_pct"] = f["mom20_pct"]  # alias used in state logic

    # 252-day high (rolling, min 200 sessions)
    f["roll252h"] = px.rolling(252, min_periods=200).max()
    f["dd_pct"] = (px / f["roll252h"] - 1.0) * 100.0
    f["dd_vel_10d"] = f["dd_pct"] - f["dd_pct"].shift(10)
    f["peak_date"] = pd.NaT  # filled later

    # Min dd over trailing 30 sessions (for crash condition)
    f["dd_min30"] = f["dd_pct"].rolling(30, min_periods=1).min()

    # --- RSI (Wilder-14) ---
    f["rsi"] = _wilder_rsi(px, n=14)

    # --- MACD(12,26,9) ---
    ema12 = px.ewm(span=12, min_periods=12).mean()
    ema26 = px.ewm(span=26, min_periods=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, min_periods=9).mean()
    f["macd_hist"] = macd_line - signal_line

    # --- Realized vol z ---
    log_ret = np.log(px / px.shift(1))
    rv21 = log_ret.rolling(21, min_periods=10).std() * np.sqrt(252)
    rv_mean = rv21.rolling(756, min_periods=252).mean()
    rv_std = rv21.rolling(756, min_periods=252).std().replace(0, np.nan)
    f["vol_z"] = (rv21 - rv_mean) / rv_std

    # --- New 252d high flag (strictly new high vs own rolling max) ---
    # A new 252d high on day i = px[i] >= roll252h[i] (within floating point)
    f["is_new_252h"] = px >= (f["roll252h"] * (1 - 1e-8))

    # --- MA20 consecutive sessions below ---
    below_ma50 = (~f["above_ma50"]).astype(int)
    # Count consecutive sessions below ma50
    # Use groupby trick
    group_id = (f["above_ma50"] != f["above_ma50"].shift(1)).cumsum()
    consecutive_below = (
        below_ma50.groupby(group_id).cumsum()
    )
    f["consec_below_ma50"] = consecutive_below * below_ma50

    return f


def _resolve_state_series(f: pd.DataFrame) -> pd.Series:
    """Resolve the state label for every row in the component frame.

    This is a vectorized approximation for the path-memory lookbacks
    (was_ext_para, macd_bear_within, lineage).  The exact per-row
    precedence is implemented here without leaking future data.
    """
    n = len(f)
    states = pd.array(["calm"] * n, dtype=object)
    states = pd.Series(states, index=f.index, dtype=object)

    # Precompute which days meet the extended/parabolic condition (for path memory)
    ext_cond = (
        (f["ext_z"] >= 2.0) |
        (f["ext_pctile"] >= 98.0) |
        (f["ext_z"] >= 1.0) |
        (f["ext_pctile"] >= 90.0)
    ).fillna(False)

    para_cond = (
        (f["ext_z"] >= 2.0) | (f["ext_pctile"] >= 98.0)
    ).fillna(False)

    ext_or_para_cond = ext_cond  # same as above (ext includes para)

    macd_sign = np.sign(f["macd_hist"].fillna(0))
    macd_bear_day = (macd_sign < 0) & (macd_sign.shift(1, fill_value=0) >= 0)
    macd_bull_day = (macd_sign > 0) & (macd_sign.shift(1, fill_value=0) <= 0)

    arr_ext_or_para = ext_or_para_cond.to_numpy()
    arr_para = para_cond.to_numpy()
    arr_dd = f["dd_pct"].to_numpy()
    arr_dd_min30 = f["dd_min30"].to_numpy()
    arr_ret20 = f["ret20_pct"].to_numpy()
    arr_mom20 = f["mom20_pct"].to_numpy()
    arr_ext_z = f["ext_z"].to_numpy()
    arr_ext_p = f["ext_pctile"].to_numpy()
    arr_above_ma20 = f["above_ma20"].to_numpy()
    arr_above_ma50 = f["above_ma50"].to_numpy()
    arr_above_ma200 = f["above_ma200"].to_numpy()
    arr_consec_below_ma50 = f["consec_below_ma50"].to_numpy()
    arr_macd_bear = macd_bear_day.to_numpy()
    arr_macd_bull = macd_bull_day.to_numpy()
    arr_is_new_h = f["is_new_252h"].to_numpy()
    arr_rsi = f["rsi"].to_numpy()

    result = np.full(n, "calm", dtype=object)

    for i in range(n):
        ret20 = arr_ret20[i] if np.isfinite(arr_ret20[i]) else 0.0
        dd = arr_dd[i] if np.isfinite(arr_dd[i]) else 0.0
        dd_min30 = arr_dd_min30[i] if np.isfinite(arr_dd_min30[i]) else 0.0
        mom20 = arr_mom20[i] if np.isfinite(arr_mom20[i]) else 0.0
        ext_z = arr_ext_z[i] if np.isfinite(arr_ext_z[i]) else 0.0
        ext_p = arr_ext_p[i] if np.isfinite(arr_ext_p[i]) else 0.0
        above_ma20 = bool(arr_above_ma20[i])
        above_ma50 = bool(arr_above_ma50[i])
        above_ma200 = bool(arr_above_ma200[i])
        consec_below50 = int(arr_consec_below_ma50[i]) if np.isfinite(arr_consec_below_ma50[i]) else 0

        # Path memory: was extended-or-parabolic within N sessions
        lo60 = max(0, i - 60)
        lo40 = max(0, i - 40)
        lo30 = max(0, i - 30)  # for crash dd lookback (already in dd_min30)
        lo10 = max(0, i - 10)

        was_ext_para_60 = bool(np.any(arr_ext_or_para[lo60:i]))
        was_ext_para_40 = bool(np.any(arr_ext_or_para[lo40:i]))

        # MACD bear cross within last 10 sessions
        macd_bear_10 = bool(np.any(arr_macd_bear[lo10:i + 1]))

        # --- State resolution (precedence order) ---

        # 1. CRASH — sticky dd clause gated on CURRENT drawdown (ITR-R5, ratified
        # 2026-07-16): without the dd<=-10 gate a V-recovery stays labeled crash
        # for 30 sessions, even at a fresh 252d high (KOSPI 2026-05-13 read
        # "crash" while AT its ATH).
        if ret20 <= -15.0 or (dd_min30 <= -18.0 and dd <= -10.0):
            result[i] = "crash"
            continue

        # 2. BREAKING
        if (was_ext_para_60 and dd <= -8.0 and not above_ma20):
            result[i] = "breaking"
            continue

        # 3. TOPPING
        # RSI divergence for this day computed inline
        rsi_div = False
        rsi_val = arr_rsi[i]
        if np.isfinite(rsi_val):
            # new 252d high within last 5 sessions (including today)
            lo5 = max(0, i - 4)
            recent_new_high = bool(np.any(arr_is_new_h[lo5:i + 1]))
            if recent_new_high:
                # Find RSI at all new-high days in prior 20-60 sessions
                lo_div_near = max(0, i - 60)
                lo_div_far = max(0, i - 20)
                # prior new highs = new highs in [lo_div_near, lo5) i.e. 20-60 sessions back
                prior_nh_slice = arr_is_new_h[lo_div_near:lo5]
                prior_rsi_slice = arr_rsi[lo_div_near:lo5]
                prior_nh_rsi = prior_rsi_slice[prior_nh_slice.astype(bool)]
                if len(prior_nh_rsi) > 0:
                    valid_rsi = prior_nh_rsi[np.isfinite(prior_nh_rsi)]
                    if len(valid_rsi) > 0:
                        max_prior_rsi = float(np.max(valid_rsi))
                        if rsi_val <= max_prior_rsi - 5.0:
                            rsi_div = True

        if (was_ext_para_40 and (rsi_div or not above_ma20 or macd_bear_10)
                and dd > -8.0):
            result[i] = "topping"
            continue

        # 4. PARABOLIC
        if ext_z >= 2.0 or (np.isfinite(arr_ext_p[i]) and ext_p >= 98.0):
            result[i] = "parabolic"
            continue

        # 5. EXTENDED
        if ext_z >= 1.0 or (np.isfinite(arr_ext_p[i]) and ext_p >= 90.0):
            result[i] = "extended"
            continue

        # 6. DOWNTREND
        if consec_below50 >= 15 and mom20 < 0:
            result[i] = "downtrend"
            continue

        # 7. RECOVERY / 8. BASING — need last non-uptrend/calm state within 60
        # We use the states already assigned before position i
        # (causal: only look at result[lo60:i])
        lo60_r = max(0, i - 60)
        prior_states = result[lo60_r:i]
        # Lineage = last non-uptrend/calm state in trailing 60
        lineage_state = None
        for ps in reversed(prior_states):
            if ps not in ("uptrend", "calm"):
                lineage_state = ps
                break

        # 7. RECOVERY
        if (lineage_state in _DOWNWARD_LINEAGE
                and above_ma50 and mom20 > 0):
            result[i] = "recovery"
            continue

        # 8. BASING
        dd_vel = f["dd_vel_10d"].iloc[i] if np.isfinite(f["dd_vel_10d"].iloc[i]) else None
        if (lineage_state in {"crash", "downtrend", "breaking"}
                and (dd_vel is None or dd_vel > -1.0)
                and above_ma20):
            result[i] = "basing"
            continue

        # 9. UPTREND
        if above_ma50 and above_ma200 and mom20 > 0:
            result[i] = "uptrend"
            continue

        # 10. CALM (default)
        result[i] = "calm"

    return pd.Series(result, index=f.index, dtype=object)


def _find_since(states: pd.Series) -> str | None:
    """First date of the current uninterrupted state run."""
    if states.empty:
        return None
    cur = states.iloc[-1]
    idx = states.index
    since_idx = len(states) - 1
    for i in range(len(states) - 2, -1, -1):
        if states.iloc[i] == cur:
            since_idx = i
        else:
            break
    return idx[since_idx].strftime("%Y-%m-%d")


def _build_events(
    f: pd.DataFrame,
    states: pd.Series,
    cutoff_sessions: int = 45,
) -> list[dict]:
    """Build the event log from the last ~45 sessions, newest first.

    All crossing signals are computed on the FULL frame first (so that the
    day immediately before the tail window supplies correct prior state), then
    filtered to the most-recent cutoff_sessions rows.  This prevents the
    tail-boundary shift(1) from producing spurious first-row events.

    First-crossing discipline: each binary condition (parabolic, crash_20d,
    ma20 above/below) fires ONLY on the day it first becomes True after being
    False.  It re-fires only after the condition has reset (returned to False
    and crossed True again).

    Event codes:
        state:<from>:<to>   — state transition
        ma20_loss           — lost 20-day average
        ma20_reclaim        — reclaimed 20-day average
        macd_bear_cross     — MACD death cross
        macd_bull_cross     — MACD golden cross
        parabolic_enter     — entered parabolic extension
        crash_20d           — fell 15%+ in 20 sessions (first crossing only)
    """
    events: list[dict] = []
    if f.empty or states.empty:
        return events

    # --- Compute all crossing signals on the FULL frame ---

    # MACD crosses (full frame)
    # Note: shift(1) on bool Series produces object dtype; cast back to bool before negation.
    macd_sign_full = np.sign(f["macd_hist"].fillna(0))
    macd_bear_full = (macd_sign_full < 0) & (macd_sign_full.shift(1, fill_value=0) >= 0)
    macd_bull_full = (macd_sign_full > 0) & (macd_sign_full.shift(1, fill_value=0) <= 0)

    # MA20 crossings (full frame) — cast prev to bool so ~ works correctly
    above20_full = f["above_ma20"].astype(bool)
    above20_prev_full = above20_full.shift(1).fillna(above20_full).astype(bool)
    ma20_loss_full = (~above20_full) & above20_prev_full
    ma20_reclaim_full = above20_full & (~above20_prev_full)

    # Parabolic first-crossing (full frame) — True only when condition transitions False→True
    para_cond_full = (
        (f["ext_z"] >= 2.0) | (f["ext_pctile"] >= 98.0)
    ).fillna(False).astype(bool)
    para_prev_full = para_cond_full.shift(1).fillna(False).astype(bool)
    para_enter_full = para_cond_full & (~para_prev_full)

    # crash_20d: first crossing only — fires when ret20 crosses <= -15% from above
    ret20_full = f["ret20_pct"]
    crash_cond_full = (ret20_full <= -15.0).astype(bool)
    crash_prev_full = crash_cond_full.shift(1).fillna(False).astype(bool)
    crash_enter_full = crash_cond_full & (~crash_prev_full)

    # --- Slice all signals to the last cutoff_sessions rows ---
    tail_idx = f.index[-cutoff_sessions:]
    tail_s = states.loc[tail_idx]

    macd_bear = macd_bear_full.loc[tail_idx]
    macd_bull = macd_bull_full.loc[tail_idx]
    ma20_loss = ma20_loss_full.loc[tail_idx]
    ma20_reclaim = ma20_reclaim_full.loc[tail_idx]
    para_enter = para_enter_full.loc[tail_idx]
    crash_enter = crash_enter_full.loc[tail_idx]

    if tail_idx.empty:
        return events

    # Build events in chronological order
    prev_state = None
    for dt in tail_idx:
        date_str = dt.strftime("%Y-%m-%d")
        cur_state = tail_s.loc[dt] if dt in tail_s.index else None

        # State transition
        if cur_state is not None and prev_state is not None and cur_state != prev_state:
            events.append({
                "date": date_str,
                "code": f"state:{prev_state}:{cur_state}",
                "en": f"State changed: {STATES.get(prev_state, {}).get('en', prev_state)} → {STATES.get(cur_state, {}).get('en', cur_state)}",
                "zh": f"状态变化：{STATES.get(prev_state, {}).get('zh', prev_state)} → {STATES.get(cur_state, {}).get('zh', cur_state)}",
            })

        # MA20 loss
        if ma20_loss.get(dt, False):
            events.append({
                "date": date_str,
                "code": "ma20_loss",
                "en": "Lost its 20-day average",
                "zh": "跌破20日均线",
            })

        # MA20 reclaim
        if ma20_reclaim.get(dt, False):
            events.append({
                "date": date_str,
                "code": "ma20_reclaim",
                "en": "Reclaimed its 20-day average",
                "zh": "收复20日均线",
            })

        # MACD bear cross
        if macd_bear.get(dt, False):
            events.append({
                "date": date_str,
                "code": "macd_bear_cross",
                "en": "Momentum turned down",
                "zh": "动能转弱",
            })

        # MACD bull cross
        if macd_bull.get(dt, False):
            events.append({
                "date": date_str,
                "code": "macd_bull_cross",
                "en": "Momentum turned up",
                "zh": "动能转强",
            })

        # Parabolic enter (first crossing: condition False→True)
        if para_enter.get(dt, False):
            events.append({
                "date": date_str,
                "code": "parabolic_enter",
                "en": "Entered parabolic extension",
                "zh": "进入抛物线超涨区",
            })

        # crash_20d: first crossing (ret20 crosses below -15%)
        if crash_enter.get(dt, False):
            events.append({
                "date": date_str,
                "code": "crash_20d",
                "en": "Fell 15%+ in 20 sessions",
                "zh": "20个交易日内跌逾15%",
            })

        if cur_state is not None:
            prev_state = cur_state

    # Newest first
    events.reverse()
    return events


def _compute_peak_rsi_memory(
    f: pd.DataFrame,
) -> tuple[Optional[float], bool, Optional[str]]:
    """Compute rsi_at_high, rsi_divergence, and peak_date from the full frame.

    rsi_at_high: RSI at the most recent 252d closing high
    rsi_divergence: new 252d high within last 5 sessions AND RSI at that high
                    <= (max RSI over prior new-high days in 20-60 sessions) - 5,
                    requiring at least one qualifying prior new-high day
    peak_date: date of the most recent 252d closing high
    """
    if f.empty:
        return None, False, None

    is_new_h = f["is_new_252h"]
    rsi_s = f["rsi"]

    # Find most recent 252d high day
    new_h_days = f.index[is_new_h]
    if len(new_h_days) == 0:
        return None, False, None

    last_new_h = new_h_days[-1]
    rsi_at_high = _safe_float(rsi_s.loc[last_new_h]) if last_new_h in rsi_s.index else None
    peak_date = last_new_h.strftime("%Y-%m-%d")

    # Divergence check: was there a new 252d high in last 5 sessions?
    last_5 = f.index[-5:]
    recent_new_high_days = [d for d in last_5 if d in new_h_days]
    rsi_divergence = False
    if recent_new_high_days and rsi_at_high is not None:
        # RSI at the most recent new high day in last 5
        rsi_recent = _safe_float(rsi_s.loc[recent_new_high_days[-1]])
        if rsi_recent is not None:
            # Prior new-high days in window 20-60 sessions back from today
            today_idx = len(f) - 1
            lo20 = max(0, today_idx - 60)
            lo5_abs = today_idx - 4  # last 5 sessions start
            prior_window = f.index[lo20:max(lo20, lo5_abs)]
            prior_nh_days = [d for d in prior_window if d in new_h_days]
            if prior_nh_days:
                prior_rsi_vals = [
                    v for d in prior_nh_days
                    if (v := _safe_float(rsi_s.loc[d])) is not None
                ]
                if prior_rsi_vals:
                    max_prior_rsi = max(prior_rsi_vals)
                    if rsi_recent <= max_prior_rsi - 5.0:
                        rsi_divergence = True

    return rsi_at_high, rsi_divergence, peak_date


def _compute_rs20(
    close: pd.Series,
    bench: pd.Series,
) -> Optional[float]:
    """20-session pct change of px/bench ratio (bench aligned by date intersection,
    ffill max 3d). Returns None if bench is None or insufficient data."""
    if bench is None or close.empty or bench.empty:
        return None
    bench_aligned = bench.reindex(close.index, method="ffill", limit=3)
    ratio = close / bench_aligned.replace(0, np.nan)
    if len(ratio.dropna()) < 21:
        return None
    rs20 = _safe_float(ratio.pct_change(20, fill_method=None).iloc[-1])
    return None if rs20 is None else rs20 * 100.0


def _compute_was_parabolic_40d(f: pd.DataFrame, states: pd.Series) -> bool:
    """True if the parabolic-level extension condition held in the trailing 40 sessions."""
    if f.empty or len(f) < 2:
        return False
    tail = min(40, len(f) - 1)
    para_cond = (
        (f["ext_z"] >= 2.0) | (f["ext_pctile"] >= 98.0)
    ).fillna(False)
    return bool(para_cond.iloc[-tail - 1:-1].any())


def _single_market(
    cc: str,
    close: pd.Series,
    bench: Optional[pd.Series],
) -> dict:
    """Compute the full state dict for one country. Fail-open."""
    close = close.dropna().sort_index()
    if len(close) < 10:
        log.warning("%s: too few rows (%d) — data_limited stub", cc, len(close))
        return _stub(data_limited=True)

    # Build component frame
    f = _compute_components(close)
    if f.empty:
        return _stub(data_limited=True)

    # Resolve state for every session (causal)
    states = _resolve_state_series(f)

    # --- Latest values ---
    latest = f.iloc[-1]
    today_state = states.iloc[-1]

    rsi_at_high, rsi_divergence, peak_date = _compute_peak_rsi_memory(f)

    # MACD state and last cross date
    macd_hist_s = f["macd_hist"]
    macd_sign = np.sign(macd_hist_s.fillna(0))
    macd_state = "bull" if macd_sign.iloc[-1] > 0 else "bear"

    # Last sign flip date (a cross ON the last session counts — review NIT 1)
    sign_change = (macd_sign != macd_sign.shift(1)).fillna(False)
    sign_change.iloc[0] = False  # series start is not a cross
    cross_days = f.index[sign_change]
    macd_cross_date = cross_days[-1].strftime("%Y-%m-%d") if len(cross_days) > 0 else None

    # Since date
    since = _find_since(states)

    # Events (last 45 sessions)
    events = _build_events(f, states, cutoff_sessions=45)

    # was_parabolic_40d
    was_parabolic_40d = _compute_was_parabolic_40d(f, states)

    # rs20_pct
    rs20_pct = _compute_rs20(close, bench)

    # ext_pctile
    ext_p_raw = latest.get("ext_pctile")
    ext_pctile = _safe_float(ext_p_raw)

    # data_limited
    data_limited = bool(latest.get("data_limited", False))
    if data_limited:
        ext_pctile = None

    state_meta = STATES.get(today_state, STATES["calm"])

    return {
        "state": today_state,
        "state_en": state_meta["en"],
        "state_zh": state_meta["zh"],
        "stance_en": state_meta["stance_en"],
        "stance_zh": state_meta["stance_zh"],
        "css": state_meta["css"],
        "since": since,
        "urgency": state_meta["urgency"],
        "ext_raw_pct": _safe_float(latest.get("ext_raw")),
        "ext_pctile": ext_pctile,
        "ext_z": _safe_float(latest.get("ext_z")),
        "mom20_pct": _safe_float(latest.get("mom20_pct")),
        "mom5_pct": _safe_float(latest.get("mom5_pct")),
        "rs20_pct": rs20_pct,
        "rsi": _safe_float(latest.get("rsi")),
        "rsi_at_high": rsi_at_high,
        "rsi_divergence": bool(rsi_divergence),
        "macd_state": macd_state,
        "macd_cross_date": macd_cross_date,
        "dd_pct": _safe_float(latest.get("dd_pct")),
        "dd_vel_10d": _safe_float(latest.get("dd_vel_10d")),
        "vol_z": _safe_float(latest.get("vol_z")),
        "above_ma20": bool(latest.get("above_ma20", False)),
        "above_ma50": bool(latest.get("above_ma50", False)),
        "above_ma200": bool(latest.get("above_ma200", False)),
        "was_parabolic_40d": was_parabolic_40d,
        "peak_date": peak_date,
        "data_limited": data_limited,
        "events": events,
    }


def _stub(data_limited: bool = True) -> dict:
    """Return a null/stub result for a country with insufficient data."""
    state_meta = STATES["calm"]
    return {
        "state": "calm",
        "state_en": state_meta["en"],
        "state_zh": state_meta["zh"],
        "stance_en": state_meta["stance_en"],
        "stance_zh": state_meta["stance_zh"],
        "css": state_meta["css"],
        "since": None,
        "urgency": 0,
        "ext_raw_pct": None,
        "ext_pctile": None,
        "ext_z": None,
        "mom20_pct": None,
        "mom5_pct": None,
        "rs20_pct": None,
        "rsi": None,
        "rsi_at_high": None,
        "rsi_divergence": False,
        "macd_state": None,
        "macd_cross_date": None,
        "dd_pct": None,
        "dd_vel_10d": None,
        "vol_z": None,
        "above_ma20": False,
        "above_ma50": False,
        "above_ma200": False,
        "was_parabolic_40d": False,
        "peak_date": None,
        "data_limited": data_limited,
        "events": [],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def market_states(
    closes: dict[str, pd.Series],
    bench: Optional[pd.Series] = None,
) -> dict[str, dict]:
    """Compute per-market turn state for each country in `closes`.

    Parameters
    ----------
    closes:
        Mapping of country code → daily close price Series (DatetimeIndex).
    bench:
        Optional benchmark Series (e.g. ^GSPC or SPY) for rs20_pct.
        When None, rs20_pct will be None for all countries.

    Returns
    -------
    dict[str, dict]
        Per-country result dict with all contract keys.  Any per-country
        exception is caught, logged, and that country is returned as a
        data_limited stub (fail-open).
    """
    results: dict[str, dict] = {}
    for cc, close in closes.items():
        try:
            results[cc] = _single_market(cc, close, bench)
        except Exception as exc:
            log.exception("%s: exception in market_states — skipping: %s", cc, exc)
            results[cc] = _stub(data_limited=True)
    return results
