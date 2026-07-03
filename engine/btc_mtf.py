"""Multi-timeframe cycle-ladder overlay for the Bitcoin Vector.

Reuses the macro dashboard's CALIBRATED cycle/MTF engine (engine.cycles) so the
Vector says the SAME thing about BTC as the stock analyzer (no second, divergent
methodology). On top of cycles.analyze(close, high, kind="crypto") it:
  * adds BIWEEKLY (2W) + MONTHLY (ME) technical timeframes (so D/3D/W/2W/ME),
  * derives a CONFLUENCE VERDICT that reconciles a short-term bounce with a
    bearish bigger picture — the exact contradiction the user flagged
    ("Counter-trend bounce within a bearish bigger picture — nimble only").

Everything is recomputed each build (like the rest of the view-model) and never
persisted. Returns {} on any failure so a short series can't break the build.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import cycles


def _long_timeframes(daily: pd.Series) -> dict:
    """Biweekly + monthly indicator states, identical shape to cycles._tf_state
    (so one UI loop renders all five). 24/7 crypto -> calendar resample; need
    >=40 resampled bars (2W ~ 560 daily, ME ~ 1200 daily)."""
    out = {}
    if len(daily) > 600:
        out["2W"] = cycles._tf_state(daily.resample("2W-MON").last().dropna())
    if len(daily) > 1200:
        out["ME"] = cycles._tf_state(daily.resample("ME").last().dropna())
    return out


def mtf_ladder(close: pd.Series, high: pd.Series) -> dict:
    """Full cycle-ladder + 5-timeframe MTF for BTC (cycles.analyze augmented with
    2W/ME). {} on any failure."""
    try:
        c = close.dropna()
        h = high.dropna()
        a = cycles.analyze(c, h, kind="crypto")
        if not a:
            return {}
        a.setdefault("mtf", {}).update(_long_timeframes(c))
        return a
    except Exception:  # noqa: BLE001 — overlay must never break the build
        return {}


def _tf_sign(tf: dict | None) -> int:
    """+1 / 0 / -1 momentum read for one timeframe state (MACD position + cross +
    RSI zone)."""
    if not tf:
        return 0
    s = 0
    s += 1 if tf.get("macd_pos") else -1
    if tf.get("macd_cross_up") or tf.get("macd_curl_up"):
        s += 1
    if tf.get("macd_cross_dn") or tf.get("macd_curl_dn"):
        s -= 1
    r = tf.get("rsi14")
    if r is not None:
        s += 1 if r >= 55 else (-1 if r <= 45 else 0)
    return int(np.sign(s))


# verdict prose, EN + ZH, keyed by (long_sign, short_sign) bucket
_VERDICTS = {
    "counter": ("Unconfirmed turn within a bearish bigger picture",
                "Short-term momentum has turned up, but the weekly/monthly trend and the cycle "
                "haven't confirmed. Most such turns fail, a minority begin a new cycle — you can't "
                "tell which until the higher timeframes confirm. High risk: small size, defined "
                "stop, not an investment-grade buy.", "CAUTION",
                "偏空大格局内的未确认转向", "短期动量已转向上行，但周线/月线趋势与周期尚未确认。"
                "多数此类转向最终失败，少数则开启新周期——在更高周期确认前无法判定。"
                "高风险：小仓位、设定止损，并非适合投资的买入。", "谨慎"),
    "dip": ("Healthy pullback within an uptrend",
            "The bigger picture is up; the short-term dip is a buy-the-dip setup, not a trend change.",
            "BUY-THE-DIP", "上升趋势内的健康回调", "大格局向上；短期回调是逢低买入的机会，而非趋势反转。", "逢低买入"),
    "trend": ("Aligned uptrend across timeframes",
              "Short and long timeframes both point up — the highest-conviction trend-follow regime.",
              "TREND-FOLLOW", "各周期一致向上", "短期与长期均指向上行 — 信心最高的顺势区间。", "顺势"),
    "avoid": ("Downtrend confirmed across timeframes",
              "Both the tape and the bigger picture are down — no edge in catching this knife.",
              "AVOID", "各周期确认下行", "盘面与大格局均向下 — 接飞刀没有优势。", "回避"),
    "wait": ("Mixed / transitional",
             "Timeframes disagree without a clear governor — wait for confluence.", "WAIT",
             "混合 / 过渡", "各周期分歧、缺乏主导 — 等待共振。", "等待"),
}


def confluence_verdict(a: dict, composite_state: str | None = None,
                       risk_on: bool | None = None) -> dict:
    """ONE verdict resolving the timeframe contradiction. Hierarchy: SHORT (daily
    /3d + ladder dir) is the tape; LONG (monthly + cycle regime + translation) is
    the governor. When they disagree it is NAMED a counter-trend move, not a
    contradiction."""
    if not a:
        return {}
    mtf = a.get("mtf", {}) or {}
    ladder = a.get("ladder", {}) or {}
    cyc = a.get("cycle", {}) or {}

    # per-timeframe MACD-trend read (honest: shows whether each timeframe's TREND
    # has turned — a bounce can be up while every timeframe's MACD is still down).
    # ME falls back to the calibrated engine's "M" when the month-end resample is
    # absent (baskets feed cycles.analyze output directly, which has no ME/2W —
    # without the fallback the verdict is BLIND to the monthly trend there).
    _me = mtf.get("ME") or mtf.get("M")
    _tfd = {"D": mtf.get("D"), "3D": mtf.get("3D"), "W": mtf.get("W"),
            "2W": mtf.get("2W"), "ME": _me}
    per_tf = {tf: ("up" if _tf_sign(d) > 0 else ("down" if _tf_sign(d) < 0 else "flat"))
              for tf, d in _tfd.items()}
    mid_sign = int(np.sign(_tf_sign(mtf.get("W")) + _tf_sign(mtf.get("2W"))))

    reg = ladder.get("regime")
    state = ladder.get("state")
    # LONG = the structural governor (cycle regime + monthly trend + cycle health)
    long_score = (2 if reg == "bull" else (-2 if reg == "bear" else 0)) + _tf_sign(_me)
    if cyc.get("translation") == "left":
        long_score -= 1
    if cyc.get("failed_cycle"):
        long_score -= 1
    long_sign = int(np.sign(long_score))

    # SHORT = the calibrated ladder tape (authoritative — it detects the bounce
    # the raw MACD signs miss, via swing-low + StochRSI pop). The WATCH states are
    # daily-driven *warnings*, not confirmed direction — when the D/3D MACD tape
    # decisively disagrees they defer to it (fix: a basket 8 days into a fresh
    # monthly cross-up printed TOP WATCH → short=-1 → "downtrend" with every
    # timeframe pointing up). DECLINE / ROLLING OVER stay authoritative.
    _bull_states = {"FRESH BUY", "TURN SIGNALED", "RALLY ON"}
    _bear_states = {"DECLINE", "ROLLING OVER"}
    _watch_states = {"TOP WATCH": -1, "BOTTOM WATCH": -1}
    _tape = int(np.sign(_tf_sign(mtf.get("D")) + _tf_sign(mtf.get("3D"))))
    if state == "COUNTERTREND BOUNCE":
        short_sign = 1
    elif state in _bull_states:
        short_sign = 1
    elif state in _bear_states:
        short_sign = -1
    elif state in _watch_states:
        short_sign = _tape if _tape != 0 else _watch_states[state]
    else:
        short_sign = _tape

    # the ladder's COUNTERTREND BOUNCE *is* the short-up/long-bear case — honour it
    if state == "COUNTERTREND BOUNCE":
        key = "counter"
    elif long_sign < 0 and short_sign > 0:
        key = "counter"
    elif long_sign > 0 and short_sign < 0:
        key = "dip"
    elif long_sign > 0 and short_sign > 0:
        key = "trend"
    elif long_sign < 0 and short_sign < 0:
        key = "avoid"
    else:
        key = "wait"
    # HONESTY GUARD — the "confirmed across timeframes" prose must never contradict
    # the per-timeframe reads on the same payload. When the ladder/cycle governor says
    # avoid but every AVAILABLE timeframe's MACD reads up (or trend-follow vs all-down),
    # the state is transitional, not confirmed — downgrade to WAIT.
    _avail = [_tf_sign(d) for d in _tfd.values() if d]
    _ups = sum(1 for s in _avail if s > 0)
    _dns = sum(1 for s in _avail if s < 0)
    if key == "avoid" and _dns == 0 and _ups >= 2:
        key = "wait"
    elif key == "trend" and _ups == 0 and _dns >= 2:
        key = "wait"
    head, sub, grade, head_zh, sub_zh, grade_zh = _VERDICTS[key]

    # when the calibrated ladder independently fired the counter-trend state,
    # use ITS verbatim entry text so the Vector and the stock analyzer match.
    if ladder.get("state") == "COUNTERTREND BOUNCE":
        et = ladder.get("entry", {}) or {}
        if et.get("text"):
            sub = et["text"]
            sub_zh = et.get("text_zh", sub_zh)

    return {
        "headline": head, "headline_zh": head_zh, "sub": sub, "sub_zh": sub_zh,
        "grade": grade, "grade_zh": grade_zh,
        "short_sign": short_sign, "mid_sign": mid_sign, "long_sign": long_sign,
        "per_tf": per_tf, "ladder_state": ladder.get("state"),
        "ladder_label": ladder.get("label"), "ladder_label_zh": ladder.get("label_zh"),
        "regime": reg, "regime_label": ladder.get("regime_label"),
        "regime_label_zh": ladder.get("regime_label_zh"),
    }
