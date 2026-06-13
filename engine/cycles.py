"""Cycle analysis + multi-timeframe technicals + the entry/exit signal ladder.

Methodology (graddhy.com, thefinancialtap.com — see DECISIONS):
- Daily cycle (DC): trough-to-trough, equities typically 36-42 trading days;
  the timing band catches ~70% of lows (that miss rate is displayed, never
  hidden). DCL = daily cycle low.
- Investor cycle (IC): 16-26 weeks, typically containing ~4-6 daily cycles.
- Swing low = price takes out the high of the candle that made the low;
  cycle-low confirmation adds: close back above the 10-day MA, and the 10-day
  MA turning up.
- Translation: where the cycle's crest fell relative to its midpoint.
  Right-translated = bullish structure; left-translated usually means the
  larger cycle has topped.
- Failed cycle: price breaks below the low that BIRTHED the current cycle —
  the single most reliable bearish tell in the framework (~80% per source).

Multi-timeframe indicators: daily, 3-day and weekly MACD(12,26,9), RSI(14),
RSI(5) and StochRSI(14) with cross detection plus *approaching-cross*
proximity (histogram trajectory), so the ladder can say "close to a turn",
not just "turned".

The ladder's per-state forward stats are measured by calibrate_ladder() and
shipped with the UI — trust levels are printed, not implied.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.technicals import macd_hist, rsi

log = logging.getLogger(__name__)

DC_BAND = (36, 42)        # equity daily cycle, trading days (timing band)
DC_EARLY = 12             # "new cycle" window after a DCL
IC_BAND_W = (16, 26)      # investor cycle, weeks
TROUGH_WINDOW = 10        # local-minimum half-window for trough detection
TROUGH_MIN_GAP = 18       # merge troughs closer than this (days)

# Per-asset-class cycle clock. Crypto trades 7 days/week with no gaps, so its
# daily cycle runs MUCH longer in calendar days than an equity's (the cycle-
# analyst convention — graddhy / thefinancialtap — is ~8-10 weeks for BTC vs
# 36-42 trading days for equities/gold). Applying the equity band to BTC made
# it read as "stretched / bottoming" far too early, and `3B` (3 business days)
# silently mishandles weekend bars — crypto uses 3-CALENDAR-day bars instead.
CYCLE_PRESETS = {
    "equity": {"dc_band": (36, 42), "dc_early": 12, "ic_band_w": (16, 26), "tf3": "3B"},
    "crypto": {"dc_band": (56, 70), "dc_early": 18, "ic_band_w": (24, 40), "tf3": "3D"},
}


def _preset(kind: str) -> dict:
    return CYCLE_PRESETS.get(kind, CYCLE_PRESETS["equity"])


# ------------------------------------------------------------ indicators ----

def stoch_rsi(close: pd.Series, n: int = 14, k: int = 3) -> pd.Series:
    r = rsi(close, n)
    lo = r.rolling(n).min()
    hi = r.rolling(n).max()
    raw = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    return raw.rolling(k).mean()


def macd_parts(close: pd.Series) -> pd.DataFrame:
    ema12 = close.ewm(span=12, min_periods=12).mean()
    ema26 = close.ewm(span=26, min_periods=26).mean()
    line = ema12 - ema26
    sig = line.ewm(span=9, min_periods=9).mean()
    return pd.DataFrame({"line": line, "signal": sig, "hist": line - sig})


def _tf_state(close: pd.Series) -> dict:
    """Indicator snapshot for one timeframe (already-resampled close)."""
    if len(close) < 40:
        return {}
    m = macd_parts(close)
    hist = m["hist"]
    r14 = rsi(close, 14)
    r5 = rsi(close, 5)
    srsi = stoch_rsi(close)
    cross_up = bool(hist.iloc[-1] > 0 and (hist.iloc[-4:-1] <= 0).any())
    cross_dn = bool(hist.iloc[-1] < 0 and (hist.iloc[-4:-1] >= 0).any())
    # approaching: histogram still negative but rising 3 bars in a row —
    # estimate bars to the zero cross from its current slope
    h = hist.dropna()
    approaching_up = approaching_dn = False
    macd_curl_up = macd_curl_dn = False
    bars_to_cross = None
    if len(h) >= 4:
        slope = (h.iloc[-1] - h.iloc[-4]) / 3
        rising = bool(h.iloc[-1] > h.iloc[-2] > h.iloc[-3])
        falling = bool(h.iloc[-1] < h.iloc[-2] < h.iloc[-3])
        if h.iloc[-1] < 0 and rising and slope > 0:
            approaching_up = True
            bars_to_cross = float(np.clip(-h.iloc[-1] / slope, 0.5, 99))
        elif h.iloc[-1] > 0 and falling and slope < 0:
            approaching_dn = True
            bars_to_cross = float(np.clip(h.iloc[-1] / -slope, 0.5, 99))
        # histogram trough/peak turn — Aspray's earliest pre-cross flag: a local
        # min in the histogram while still below zero (1 confirming up-bar)
        macd_curl_up = bool(h.iloc[-1] < 0 and h.iloc[-1] > h.iloc[-2] <= h.iloc[-3])
        macd_curl_dn = bool(h.iloc[-1] > 0 and h.iloc[-1] < h.iloc[-2] >= h.iloc[-3])

    # StochRSI popping out of oversold/overbought — the earliest oscillator heads-up
    sclean = srsi.dropna()
    stoch_cross_up = bool(len(sclean) >= 4 and sclean.iloc[-1] >= 20
                          and (sclean.iloc[-4:-1] < 20).any())
    stoch_cross_dn = bool(len(sclean) >= 4 and sclean.iloc[-1] <= 80
                          and (sclean.iloc[-4:-1] > 80).any())
    def _spark(s: pd.Series, n: int = 20, dec: int = 1) -> list:
        return [round(float(x), dec) for x in s.dropna().iloc[-n:]]

    return {
        "macd_pos": bool(hist.iloc[-1] > 0),
        "macd_cross_up": cross_up, "macd_cross_dn": cross_dn,
        "macd_approaching_up": approaching_up, "macd_approaching_dn": approaching_dn,
        "macd_curl_up": macd_curl_up, "macd_curl_dn": macd_curl_dn,
        "macd_bars_to_cross": round(bars_to_cross, 1) if bars_to_cross else None,
        "stoch_cross_up": stoch_cross_up, "stoch_cross_dn": stoch_cross_dn,
        "rsi14": round(float(r14.iloc[-1]), 0) if pd.notna(r14.iloc[-1]) else None,
        "rsi5": round(float(r5.iloc[-1]), 0) if pd.notna(r5.iloc[-1]) else None,
        "stoch": round(float(srsi.iloc[-1]), 0) if pd.notna(srsi.iloc[-1]) else None,
        # compact recent series for client-side sparklines (gauges + histogram)
        "spark_rsi": _spark(r14), "spark_stoch": _spark(srsi),
        "spark_hist": _spark(hist, dec=3),
    }


def mtf_snapshot(close: pd.Series, kind: str = "equity") -> dict:
    """Daily / 3-day / weekly indicator states. The 3-day bar respects the
    asset's trading calendar (business days for equities, calendar days for
    24/7 crypto)."""
    daily = close.dropna()
    tf3 = _preset(kind)["tf3"]
    return {
        "D": _tf_state(daily),
        "3D": _tf_state(daily.resample(tf3).last().dropna()) if len(daily) > 150 else {},
        "W": _tf_state(daily.resample("W-FRI").last().dropna()) if len(daily) > 300 else {},
    }


# ---------------------------------------------------------------- cycles ----

def find_troughs(close: pd.Series, window: int = TROUGH_WINDOW,
                 min_gap: int = TROUGH_MIN_GAP) -> list[pd.Timestamp]:
    """Cycle troughs: local minima confirmed by both sides, merged when too
    close (keep the lower). The most recent <window> days can't confirm yet."""
    c = close.dropna()
    if len(c) < window * 3:
        return []
    arr = c.to_numpy()
    idx = []
    for i in range(window, len(arr) - window):
        seg = arr[i - window: i + window + 1]
        if arr[i] == seg.min():
            idx.append(i)
    # merge near-duplicates
    merged: list[int] = []
    for i in idx:
        if merged and (i - merged[-1]) < min_gap:
            if arr[i] < arr[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return [c.index[i] for i in merged]


def cycle_state(close: pd.Series, high: pd.Series | None = None,
                kind: str = "equity") -> dict:
    """Daily + investor cycle position for one instrument."""
    c = close.dropna()
    if len(c) < 260:
        return {}
    p = _preset(kind)
    dc_band, dc_early, ic_band_w = p["dc_band"], p["dc_early"], p["ic_band_w"]
    troughs = find_troughs(c)
    if not troughs:
        return {}
    last_dcl = troughs[-1]
    dc_day = int(len(c.loc[last_dcl:]) - 1)
    dcl_price = float(c.loc[last_dcl])

    # candidate for the NEXT cycle low: the lowest bar of the recent decline.
    # Only meaningful once the cycle is old enough that a new low is due.
    cand_day = cand_price = cand_swing = cand_age = None
    if dc_day >= dc_band[0] - 10:
        recent = c.iloc[-25:]
        cand_ts = recent.idxmin()
        cand_price = float(recent.min())
        cand_age = int(len(c.loc[cand_ts:]) - 1)
        cand_day = str(cand_ts.date())
        ref = (high if high is not None else close).dropna()
        if cand_ts in ref.index and cand_age >= 1:
            bar_high = float(ref.loc[cand_ts])
            cand_swing = bool((c.loc[cand_ts:].iloc[1:] > bar_high).any())
        else:
            cand_swing = False

    # translation of the LAST COMPLETED cycle
    translation = None
    if len(troughs) >= 2:
        seg = c.loc[troughs[-2]:troughs[-1]]
        if len(seg) > 10:
            crest_pos = seg.to_numpy().argmax() / (len(seg) - 1)
            translation = ("right" if crest_pos > 0.55 else
                           "left" if crest_pos < 0.45 else "middle")

    failed = bool(c.iloc[-1] < dcl_price)
    # how long the failure has been in force: bars since price first closed
    # below the low that birthed this cycle (drives the "failed N days ago" line)
    failed_age = None
    if failed:
        seg = c.loc[last_dcl:]
        below = seg[seg < dcl_price]
        if len(below):
            failed_age = int(len(seg.loc[below.index[0]:]) - 1)

    # swing low off the lowest candle of the current decline (uses highs if given)
    swing_low = None
    lowest_day = c.loc[last_dcl:].idxmin()
    ref = (high if high is not None else close)
    ref = ref.dropna()
    if lowest_day in ref.index:
        bar_high = float(ref.loc[lowest_day])
        after = c.loc[lowest_day:].iloc[1:]
        swing_low = bool((after > bar_high).any()) if len(after) else False

    ma10 = c.rolling(10).mean()
    above_ma10 = bool(c.iloc[-1] > ma10.iloc[-1])
    ma10_rising = bool(ma10.iloc[-1] > ma10.iloc[-3])

    # investor cycle from weekly bars
    w = c.resample("W-FRI").last().dropna()
    wt = find_troughs(w, window=6, min_gap=8)
    ic_week = int(len(w.loc[wt[-1]:]) - 1) if wt else None
    ic_failed = bool(wt and w.iloc[-1] < float(w.loc[wt[-1]])) if wt else False

    if dc_day < dc_early:
        dc_phase = "new"
    elif dc_day < dc_band[0] - 8:
        dc_phase = "mid"
    elif dc_day < dc_band[0]:
        dc_phase = "approaching_band"
    elif dc_day <= dc_band[1]:
        dc_phase = "in_band"
    else:
        dc_phase = "stretched"

    ic_phase = None
    if ic_week is not None:
        ic_late = round(ic_band_w[1] * 0.5)
        ic_phase = ("early" if ic_week <= 6 else "mid" if ic_week <= ic_late else
                    "late" if ic_week <= ic_band_w[1] else "overdue")

    return {
        "dc_day": dc_day, "dc_band": dc_band, "dc_early": dc_early, "dc_phase": dc_phase,
        "last_dcl": str(last_dcl.date()), "dcl_price": round(dcl_price, 2),
        "cand_dcl": cand_day, "cand_price": round(cand_price, 2) if cand_price else None,
        "cand_swing": cand_swing, "cand_age": cand_age,
        "translation": translation, "failed_cycle": failed, "failed_age": failed_age,
        "swing_low": swing_low, "above_ma10": above_ma10, "ma10_rising": ma10_rising,
        "ic_week": ic_week, "ic_band": ic_band_w, "ic_phase": ic_phase, "ic_failed": ic_failed,
        "n_troughs": len(troughs),
    }


# --------------------------------------------------- pre-emptive detection ----

def _pivots(s: np.ndarray, k: int, kind: str) -> list[int]:
    """Confirmed pivot indices: extremum of k bars each side. The last k bars
    can't confirm yet (no look-ahead)."""
    out = []
    for i in range(k, len(s) - k):
        seg = s[i - k: i + k + 1]
        if (kind == "low" and s[i] == seg.min()) or (kind == "high" and s[i] == seg.max()):
            out.append(i)
    return out


def rsi_divergence(close: pd.Series, k: int = 5, min_dist: int = 13,
                   max_dist: int = 60, mag: float = 4.0) -> dict:
    """Regular RSI(14) divergence between the two most recent confirmed pivots,
    with the junk filters the research flagged as load-bearing: both legs near
    the oscillator extreme, a minimum RSI magnitude, and a min/max pivot spacing.
    Bullish = price lower-low while RSI higher-low (mirror for bearish)."""
    c = close.dropna()
    if len(c) < k * 3 + 30:
        return {}
    r = rsi(c, 14)
    arr, rv = c.to_numpy(), r.to_numpy()
    out: dict = {}
    last = len(c) - 1

    plo = _pivots(arr, k, "low")
    if len(plo) >= 2:
        p1, p2 = plo[-2], plo[-1]
        if (min_dist <= p2 - p1 <= max_dist and last - p2 <= max_dist
                and arr[p2] < arr[p1] and rv[p2] > rv[p1] + mag
                and rv[p1] < 40 and rv[p2] < 48):
            out["bull"] = True
            out["bull_bars_ago"] = int(last - p2)

    phi = _pivots(arr, k, "high")
    if len(phi) >= 2:
        p1, p2 = phi[-2], phi[-1]
        if (min_dist <= p2 - p1 <= max_dist and last - p2 <= max_dist
                and arr[p2] > arr[p1] and rv[p2] < rv[p1] - mag
                and rv[p1] > 60 and rv[p2] > 52):
            out["bear"] = True
            out["bear_bars_ago"] = int(last - p2)
    return out


def early_signals(close: pd.Series, cyc: dict, mtf: dict) -> dict:
    """Anticipatory tier — the pre-emptive layer that fires BEFORE full cycle
    confirmation. Gated by cycle context so it can't scream 'buy' in free-fall:
    bullish signals only count when a low is plausibly near (in/after the timing
    band, or short-term washed out); bearish only when extended/late. Returned as
    explicit named signals + a tier, never as a standalone buy. Calibrated
    separately (see calibrate_ladder) so its real edge is measured, not assumed."""
    d = mtf.get("D", {})
    if not d or not cyc:
        return {}
    div = rsi_divergence(close)
    late = cyc.get("dc_phase") in ("approaching_band", "in_band", "stretched")
    washed = (d.get("rsi5") or 50) < 25 or (d.get("stoch") or 50) < 12
    extended = cyc.get("dc_phase") in ("mid", "approaching_band", "in_band", "stretched") \
        and cyc.get("above_ma10")
    overbought = (d.get("rsi14") or 50) > 70 or (d.get("stoch") or 50) > 88

    bull, bear = [], []
    if (late or washed) and not cyc.get("failed_cycle"):
        if div.get("bull"):
            bull.append("RSI bullish divergence (price made a lower low, momentum didn't)")
        if d.get("macd_curl_up"):
            bull.append("MACD histogram turned up off a trough (pre-cross)")
        if d.get("stoch_cross_up"):
            bull.append("StochRSI popped out of oversold")
    if extended and overbought:
        if div.get("bear"):
            bear.append("RSI bearish divergence (price made a higher high, momentum didn't)")
        if d.get("macd_curl_dn"):
            bear.append("MACD histogram rolled over off a peak (pre-cross)")
        if d.get("stoch_cross_dn"):
            bear.append("StochRSI dropped out of overbought")

    if bull and not bear:
        tier = "anticipated" if (div.get("bull") or len(bull) >= 2) else "heads-up"
        return {"dir": "up", "tier": tier, "signals": bull, "n": len(bull)}
    if bear and not bull:
        tier = "anticipated" if (div.get("bear") or len(bear) >= 2) else "heads-up"
        return {"dir": "down", "tier": tier, "signals": bear, "n": len(bear)}
    return {}


# ----------------------------------------------------------- signal ladder ----

LADDER = ["DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY",
          "RALLY ON", "TOP WATCH", "ROLLING OVER", "COUNTERTREND BOUNCE"]

LADDER_SCORE = {"DECLINE": -80, "ROLLING OVER": -40, "TOP WATCH": -10,
                "BOTTOM WATCH": 10, "TURN SIGNALED": 45, "FRESH BUY": 80,
                "RALLY ON": 55, "COUNTERTREND BOUNCE": -25}

# Plain, direction-explicit display for every internal state. The bottom and
# top "turns" are deliberately named as mirror images (BOTTOMING = buy setup,
# TOPPING = sell setup) so the symmetry is obvious. Internal keys above stay
# fixed so the calibration JSON keeps matching. action = one-word call.
STATE_DISPLAY = {
    "DECLINE":       {"label": "DOWNTREND",     "action": "AVOID",        "dir": "down",
                      "label_zh": "下跌趋势", "action_zh": "回避"},
    "BOTTOM WATCH":  {"label": "NEARING A LOW",  "action": "GET READY",    "dir": "down",
                      "label_zh": "接近低点", "action_zh": "准备"},
    "TURN SIGNALED": {"label": "BOTTOMING",      "action": "BUY SETUP",    "dir": "up",
                      "label_zh": "筑底中", "action_zh": "买入预备"},
    "FRESH BUY":     {"label": "BUY ZONE",       "action": "BUY",          "dir": "up",
                      "label_zh": "买入区", "action_zh": "买入"},
    "RALLY ON":      {"label": "UPTREND",        "action": "HOLD",         "dir": "up",
                      "label_zh": "上涨趋势", "action_zh": "持有"},
    "TOP WATCH":     {"label": "NEARING A HIGH", "action": "TAKE PROFITS", "dir": "up",
                      "label_zh": "接近高点", "action_zh": "止盈"},
    "ROLLING OVER":  {"label": "TOPPING",        "action": "SELL SETUP",   "dir": "down",
                      "label_zh": "做顶中", "action_zh": "卖出预备"},
    # daily bottoming setup INSIDE a bearish higher-timeframe regime: a real
    # bounce may come, but it's counter-trend and high-risk — never a "buy".
    "COUNTERTREND BOUNCE": {"label": "COUNTER-TREND BOUNCE",
                            "action": "HIGH-RISK · NIMBLE ONLY", "dir": "caution",
                            "label_zh": "逆势反弹", "action_zh": "高风险 · 仅限灵活操作"},
}

# Daily-cycle phase -> plain-language descriptor (answers "are we overextended?")
DC_PHASE_PLAIN = {
    "new": "fresh — a new cycle just started",
    "mid": "mid-cycle — trending",
    "approaching_band": "approaching the window where lows usually form",
    "in_band": "inside the window where a low is due",
    "stretched": "overdue — past the typical window, so a low could form any day",
}
IC_PHASE_PLAIN = {
    "early": "early — lots of room left in the bigger up-leg",
    "mid": "mid — the bigger up-leg is maturing",
    "late": "late — the bigger cycle is getting old",
    "overdue": "overdue — the bigger cycle is stretched, expect more volatility",
}

# Parallel Chinese phase descriptors (same keys; English fallback at call sites).
DC_PHASE_PLAIN_ZH = {
    "new": "全新——新周期刚刚启动",
    "mid": "周期中段——趋势运行中",
    "approaching_band": "接近低点通常形成的时间窗口",
    "in_band": "处于低点应当出现的时间窗口内",
    "stretched": "逾期——已超过典型窗口，低点随时可能形成",
}
IC_PHASE_PLAIN_ZH = {
    "early": "早期——更大的上行段仍有充足空间",
    "mid": "中期——更大的上行段正在成熟",
    "late": "晚期——更大的周期已趋于老化",
    "overdue": "逾期——更大的周期已被拉伸，预计波动加剧",
}


def cycle_plain(cyc: dict) -> dict:
    """Human-readable daily vs weekly cycle context — kept distinct so users
    always know which clock they're reading."""
    lo, hi = cyc.get("dc_band", DC_BAND)
    out = {
        "daily_line": f"Daily cycle: day {cyc.get('dc_day', '?')} of a typical {lo}–{hi} trading days",
        "daily_phase": DC_PHASE_PLAIN.get(cyc.get("dc_phase"), ""),
        "daily_line_zh": f"日线周期：第 {cyc.get('dc_day', '?')} 天，典型周期为 {lo}–{hi} 个交易日",
        "daily_phase_zh": DC_PHASE_PLAIN_ZH.get(cyc.get("dc_phase"),
                                                DC_PHASE_PLAIN.get(cyc.get("dc_phase"), "")),
    }
    if cyc.get("ic_week") is not None:
        ic_lo, ic_hi = cyc.get("ic_band", IC_BAND_W)
        out["weekly_line"] = (f"Weekly (investor) cycle: week {cyc['ic_week']} of a typical "
                              f"{ic_lo}–{ic_hi} weeks")
        out["weekly_phase"] = IC_PHASE_PLAIN.get(cyc.get("ic_phase"), "")
        out["weekly_line_zh"] = (f"周线（投资者）周期：第 {cyc['ic_week']} 周，典型周期为 "
                                 f"{ic_lo}–{ic_hi} 周")
        out["weekly_phase_zh"] = IC_PHASE_PLAIN_ZH.get(cyc.get("ic_phase"),
                                                       IC_PHASE_PLAIN.get(cyc.get("ic_phase"), ""))
    tr = cyc.get("translation")
    if tr == "left":
        out["translation"] = ("The last cycle peaked in its FIRST half ('left-translated') — "
                              "weak cycles top early, so this hints the bigger trend is tiring.")
        out["translation_zh"] = ("上一周期在前半段见顶（“左移”）——弱周期见顶偏早，"
                                 "这暗示更大的趋势正在走弱。")
    elif tr == "right":
        out["translation"] = ("The last cycle peaked in its SECOND half ('right-translated') — "
                              "strong cycles top late, a healthy-uptrend sign.")
        out["translation_zh"] = ("上一周期在后半段见顶（“右移”）——强周期见顶偏晚，"
                                 "属于健康上涨趋势的信号。")
    elif tr == "middle":
        out["translation"] = "The last cycle peaked mid-way — a neutral, balanced structure."
        out["translation_zh"] = "上一周期在中段见顶——结构中性、均衡。"
    return out


def entry_timing(state: str, cyc: dict, mtf: dict) -> dict:
    """Actionable timing call + a rough days-to-entry estimate from cycle
    position and the MACD cross trajectory. Clearly an estimate, ranged."""
    d = mtf.get("D", {})
    lo_band, hi_band = cyc.get("dc_band", DC_BAND)
    dc = cyc.get("dc_day", 0)
    btc = d.get("macd_bars_to_cross")

    if state == "COUNTERTREND BOUNCE":
        inval = cyc.get("cand_price") or cyc.get("dcl_price")
        return {"tag": "BOUNCE — HIGH RISK", "urgency": "caution",
                "text": "Counter-trend bounce inside a bearish bigger picture. For nimble "
                        f"traders only — small size, tight stop below {inval}. If the daily "
                        "low fails it cascades toward the larger cycle low; not an investment buy.",
                "text_zh": "处于看空大局中的逆势反弹。仅限灵活交易者——小仓位、"
                           f"将止损紧贴 {inval} 下方。若日线低点失守，将向更大周期低点蔓延；"
                           "并非投资性买入。"}
    if state == "FRESH BUY":
        return {"tag": "BUY NOW", "urgency": "now",
                "text": "Confirmed cycle low — the entry window is open now, "
                        f"with a clear exit if it closes back below {cyc.get('cand_price') or cyc.get('dcl_price')}.",
                "text_zh": "周期低点已确认——入场窗口现已开启，"
                           f"若收盘重新跌破 {cyc.get('cand_price') or cyc.get('dcl_price')} 则明确离场。"}
    if state == "TURN SIGNALED":
        lo, hi = (1, max(2, round(btc))) if btc else (1, 3)
        return {"tag": "BUY SOON", "urgency": "imminent", "days_lo": lo, "days_hi": hi,
                "text": f"Setup almost complete — likely buy trigger in ~{lo}–{hi} trading days "
                        "if it closes back above its 10-day average.",
                "text_zh": f"形态接近完成——若收盘重新站上 10 日均线，预计将在约 {lo}–{hi} 个交易日内"
                           "出现买入触发。"}
    if state == "BOTTOM WATCH":
        if cyc.get("dc_phase") in ("approaching_band", "in_band", "stretched"):
            lo = max(lo_band - dc, 0)
            hi = max(hi_band - dc, lo + 2)
            if btc:
                hi = min(hi, round(btc) + 3)
                lo = min(lo, max(round(btc) - 1, 1))
            rng = f"~{lo}–{hi}" if lo != hi else f"~{hi}"
            return {"tag": "WATCH", "urgency": "soon", "days_lo": lo, "days_hi": hi,
                    "text": f"A cycle low is due in roughly {rng} trading days — watch for the "
                            "turn, don't front-run it.",
                    "text_zh": f"周期低点预计在约 {rng} 个交易日内出现——等待转向，切勿抢跑。"}
        # early/mid-cycle dip below the 10-day average — NOT the cycle low yet
        far = max(lo_band - dc, 2)
        return {"tag": "WAIT", "urgency": "later", "days_lo": far, "days_hi": hi_band - dc,
                "text": f"A normal mid-cycle dip below the 10-day average — the real cycle low "
                        f"isn't due for ~{far}+ trading days. Wait for support to hold, or for "
                        "the next low to set up.",
                "text_zh": f"这是跌破 10 日均线的正常周期中段回调——真正的周期低点要到约 {far}+ "
                           "个交易日后才会到来。等待支撑站稳，或等下一个低点构筑成形。"}
    if state == "RALLY ON":
        late = dc >= lo_band - 8
        return {"tag": "HOLD", "urgency": "hold",
                "text": ("Trend intact — hold. Late in the cycle, so don't add here; a pullback is due."
                         if late else "Trend intact — hold; add on dips toward the 10-day average."),
                "text_zh": ("趋势完好——持有。已处周期晚期，此处不宜加仓；回调即将到来。"
                            if late else "趋势完好——持有；可在回调至 10 日均线附近时加仓。")}
    if state == "TOP WATCH":
        return {"tag": "TAKE PROFITS", "urgency": "caution",
                "text": "Stretched/late — protect gains and don't start new positions; "
                        "let the next low set up first.",
                "text_zh": "已拉伸／晚期——保护利润，不要新开仓；先等下一个低点构筑成形。"}
    if state == "ROLLING OVER":
        return {"tag": "SELL / REDUCE", "urgency": "exit",
                "text": "Momentum rolled over and the 10-day average is lost — reduce or tighten stops.",
                "text_zh": "动量已掉头向下且失守 10 日均线——减仓或收紧止损。"}
    return {"tag": "AVOID", "urgency": "avoid",
            "text": "Downtrend — stand aside until a new cycle low forms and confirms.",
            "text_zh": "下跌趋势——观望，直至新的周期低点形成并确认。"}


REGIME_DISPLAY = {
    "bull": {"label": "BULLISH", "word": "with-trend",
             "label_zh": "看多", "word_zh": "顺势"},
    "neutral": {"label": "MIXED", "word": "no clear trend",
                "label_zh": "混合", "word_zh": "趋势不明"},
    "bear": {"label": "BEARISH", "word": "counter-trend",
             "label_zh": "看空", "word_zh": "逆势"},
}


def regime_state(cyc: dict, mtf: dict) -> dict:
    """The DOMINANT higher-timeframe context — bull / neutral / bear — built
    from the weekly + 3-day MACD and the investor-cycle health. This is the
    'regime' the daily-timeframe 'tactical' signal lives inside: a daily buy
    setup means very different things in a bull vs a bear regime. Kept separate
    so the UI can say 'short-term up, bigger picture down' instead of collapsing
    a genuinely two-dimensional read into one misleading label."""
    if not cyc:
        return {"regime": "neutral", "score": 0.0, "why": ""}
    w, t3 = mtf.get("W", {}), mtf.get("3D", {})
    why = []
    s = 0.0
    # weekly momentum dominates
    if w:
        if w.get("macd_cross_dn"):
            s -= 2.0; why.append("weekly momentum just crossed down")
        elif w.get("macd_cross_up"):
            s += 2.0; why.append("weekly momentum just crossed up")
        elif w.get("macd_pos"):
            s += 1.0; why.append("weekly momentum positive")
            if w.get("macd_approaching_dn"):
                s -= 0.5; why.append("but rolling toward a weekly cross-down")
        elif w.get("macd_approaching_up"):
            s += 0.5; why.append("weekly momentum curling up")
        else:
            s -= 1.0; why.append("weekly momentum negative")
    # 3-day confirms / tempers
    if t3:
        if t3.get("macd_cross_dn"):
            s -= 1.0; why.append("3-day crossed down")
        elif t3.get("macd_cross_up"):
            s += 1.0; why.append("3-day crossed up")
        elif t3.get("macd_pos"):
            s += 0.5
        else:
            s -= 0.5
    # investor cycle health is the structural backbone
    if cyc.get("ic_failed"):
        s -= 2.0; why.append("investor cycle failed (broke its start low)")
    icp = cyc.get("ic_phase")
    if icp == "early":
        s += 1.0
    elif icp == "late":
        s -= 1.0
    elif icp == "overdue":
        s -= 1.5; why.append("investor cycle overdue")
    if cyc.get("translation") == "left":
        s -= 1.0; why.append("last cycle left-translated (topped early)")
    elif cyc.get("translation") == "right":
        s += 0.5

    regime = "bear" if s <= -1.5 else "bull" if s >= 1.5 else "neutral"
    return {"regime": regime, "score": round(s, 1),
            "label": REGIME_DISPLAY[regime]["label"], "why": "; ".join(why)}


def ladder_state(cyc: dict, mtf: dict, early: dict | None = None) -> dict:
    """Combine cycle position + multi-timeframe indicators into one state,
    with a plain next-step line. The higher-timeframe regime (weekly + 3-day +
    investor cycle) gates and can RE-LABEL the daily signal: a daily buy setup
    inside a bearish regime is a counter-trend bounce, not a buy."""
    if not cyc or not mtf.get("D"):
        return {}
    early = early or {}
    d, w = mtf["D"], mtf.get("W", {})
    regime = regime_state(cyc, mtf)
    # full conviction only in a bull regime; otherwise the daily setup is partial
    weekly_ok = regime["regime"] == "bull"

    lo_b, hi_b = cyc.get("dc_band", DC_BAND)
    dc_early = cyc.get("dc_early", DC_EARLY)
    state, why, nxt = None, "", ""
    why_zh, nxt_zh = "", ""
    late = cyc["dc_phase"] in ("approaching_band", "in_band", "stretched")
    # a late-cycle decline hunts the NEXT low via the candidate trough
    cand_confirmed = bool(late and cyc.get("cand_swing") and cyc["above_ma10"])

    if cyc["failed_cycle"] and not cyc["above_ma10"]:
        state = "DECLINE"
        why = ("Failed cycle — price broke below the low that started this cycle, "
               "which historically means the larger trend is rolling over (~80% of cases).")
        nxt = "Stand aside until a new daily cycle low forms and confirms."
        why_zh = ("失败周期——价格跌破了启动本周期的低点，"
                  "历史上这通常意味着更大的趋势正在掉头向下（约 80% 的情形）。")
        nxt_zh = "观望，直至新的日线周期低点形成并确认。"
    elif cand_confirmed and (d.get("macd_cross_up") or d.get("macd_pos")
                             or d.get("macd_approaching_up")):
        state = "FRESH BUY" if weekly_ok else "TURN SIGNALED"
        why = (f"A new cycle low likely formed {cyc['cand_age']} day(s) ago "
               f"({cyc['cand_dcl']} @ {cyc['cand_price']}): swing low in, price back "
               "above the 10-day average"
               + (" — and the weekly timeframe agrees." if weekly_ok else
                  " — but the weekly timeframe hasn't turned yet, so conviction is partial."))
        why_zh = (f"新的周期低点可能已在 {cyc['cand_age']} 天前形成 "
                  f"（{cyc['cand_dcl']} @ {cyc['cand_price']}）：摆动低点已现，价格重新"
                  "站上 10 日均线"
                  + ("——且周线周期也一致确认。" if weekly_ok else
                     "——但周线周期尚未转向，因此信心仅为部分。"))
        nxt = (f"The cleanest setup cycle logic offers — entry with a defined exit: "
               f"invalidation = a close below {cyc['cand_price']}.") if weekly_ok else \
              "Either wait for the weekly to turn, or size half until it does."
        nxt_zh = (f"周期逻辑所能给出的最干净形态——入场并设有明确离场："
                  f"失效点 = 收盘跌破 {cyc['cand_price']}。") if weekly_ok else \
                 "可等待周线转向，或在其转向前先建半仓。"
    elif late and cyc.get("cand_swing") and not cyc["above_ma10"]:
        state = "TURN SIGNALED"
        why = (f"Buyers rejected the {cyc['cand_dcl']} low (swing low printed) but price "
               "hasn't reclaimed its 10-day average — first box ticked, not all.")
        why_zh = (f"买方拒绝了 {cyc['cand_dcl']} 的低点（摆动低点已现），但价格"
                  "尚未收复 10 日均线——第一项条件达成，并非全部。")
        nxt = "Confirmation = a close above the 10-day average with the average turning up."
        nxt_zh = "确认 = 收盘站上 10 日均线且均线开始向上。"
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            nxt += f" Daily momentum is ~{d['macd_bars_to_cross']:.0f} bars from its bullish cross."
            nxt_zh += f" 日线动量距其看多交叉约 {d['macd_bars_to_cross']:.0f} 根 K 线。"
    elif late and not cyc["above_ma10"]:
        state = "BOTTOM WATCH"
        why = (f"Day {cyc['dc_day']} of a typical {lo_b}-{hi_b}-day cycle — "
               "inside the window where lows usually form"
               + (", and short-term momentum is washed out" if (d.get("rsi5") or 50) < 30 else "")
               + ". No confirmed turn yet.")
        why_zh = (f"典型 {lo_b}-{hi_b} 天周期的第 {cyc['dc_day']} 天——"
                  "处于低点通常形成的窗口内"
                  + ("，且短期动量已被洗净" if (d.get("rsi5") or 50) < 30 else "")
                  + "。尚无确认的转向。")
        nxt = ("Wait for the turn: a move above the low candle's high, then a close back "
               "above the 10-day average.")
        nxt_zh = "等待转向：先上破低点 K 线的高点，再收盘重新站上 10 日均线。"
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            nxt += f" Daily momentum is ~{d['macd_bars_to_cross']:.0f} bars from a bullish cross."
            nxt_zh += f" 日线动量距看多交叉约 {d['macd_bars_to_cross']:.0f} 根 K 线。"
    elif d.get("macd_cross_dn") and not cyc["above_ma10"] and cyc["dc_day"] > dc_early:
        state = "ROLLING OVER"
        why = "Daily momentum just crossed down and price lost its 10-day average mid-cycle."
        why_zh = "日线动量刚刚向下交叉，且价格在周期中段失守 10 日均线。"
        nxt = ("Trim or tighten stops; next likely support is the daily-cycle timing band "
               f"(~day {lo_b}-{hi_b}, now day {cyc['dc_day']}).")
        nxt_zh = ("减仓或收紧止损；下一个可能的支撑是日线周期的时间窗口 "
                  f"（约第 {lo_b}-{hi_b} 天，现为第 {cyc['dc_day']} 天）。")
    elif cyc["swing_low"] and cyc["dc_day"] <= dc_early and cyc["above_ma10"] \
            and (d.get("macd_cross_up") or d.get("macd_pos")):
        state = "FRESH BUY" if weekly_ok else "TURN SIGNALED"
        why = (f"New daily cycle, day {cyc['dc_day']}: swing low in, price back above the "
               "10-day average, daily momentum positive"
               + (" — and the weekly timeframe agrees." if weekly_ok else
                  " — but the weekly timeframe hasn't turned yet, so conviction is partial."))
        why_zh = (f"新的日线周期，第 {cyc['dc_day']} 天：摆动低点已现，价格重新站上 "
                  "10 日均线，日线动量为正"
                  + ("——且周线周期也一致确认。" if weekly_ok else
                     "——但周线周期尚未转向，因此信心仅为部分。"))
        nxt = ("The highest-odds window by cycle logic; invalidation = a close below "
               f"the cycle low ({cyc['dcl_price']}).") if weekly_ok else \
              "Either wait for the weekly to turn, or size half until it does."
        nxt_zh = ("按周期逻辑胜率最高的窗口；失效点 = 收盘跌破"
                  f"周期低点（{cyc['dcl_price']}）。") if weekly_ok else \
                 "可等待周线转向，或在其转向前先建半仓。"
    elif cyc["above_ma10"] and cyc["ma10_rising"] and not late:
        hot = []
        if (d.get("rsi14") or 50) > 70:
            hot.append(f"RSI {d.get('rsi14'):.0f}")
        if (d.get("stoch") or 50) > 90:
            hot.append(f"StochRSI {d.get('stoch'):.0f}")
        if hot:
            state = "TOP WATCH"
            why = (f"Mid-cycle (day {cyc['dc_day']}) and short-term overbought "
                   f"({', '.join(hot)}).")
            why_zh = (f"周期中段（第 {cyc['dc_day']} 天）且短期超买 "
                      f"（{', '.join(hot)}）。")
            nxt = ("Not a short signal — just don't add here; pullbacks to the 10-day "
                   "average are normal.")
            nxt_zh = "并非做空信号——只是此处不宜加仓；回调至 10 日均线属于正常现象。"
        else:
            state = "RALLY ON"
            why = (f"Day {cyc['dc_day']} of the cycle, trend intact above a rising 10-day average"
                   + (", weekly aligned." if weekly_ok else ", weekly still mixed."))
            why_zh = (f"周期第 {cyc['dc_day']} 天，趋势完好并位于向上的 10 日均线之上"
                      + ("，周线一致。" if weekly_ok else "，周线仍为混合。"))
            nxt = ("Hold; first warning would be losing the 10-day average, bigger warning is a "
                   "daily momentum cross down.")
            nxt_zh = "持有；首个预警是失守 10 日均线，更大的预警是日线动量向下交叉。"
    elif late and cyc["above_ma10"]:
        state = "TOP WATCH"
        why = (f"Late in the daily cycle (day {cyc['dc_day']} of ~{lo_b}-{hi_b}) — "
               "odds favor a dip into the next cycle low from here even with the trend intact.")
        why_zh = (f"处于日线周期晚期（约 {lo_b}-{hi_b} 天中的第 {cyc['dc_day']} 天）——"
                  "即便趋势完好，从此处概率上仍倾向于回落至下一个周期低点。")
        nxt = "Let the next daily cycle low form before adding; watch for the swing-low setup."
        nxt_zh = "在加仓前先让下一个日线周期低点形成；留意摆动低点形态。"
    else:
        state = "RALLY ON" if cyc["above_ma10"] else "BOTTOM WATCH"
        why = "Mixed structure."
        why_zh = "结构混合。"
        nxt = "Watch the 10-day average and cycle-day count."
        nxt_zh = "关注 10 日均线与周期天数。"

    # ── Regime gate ─────────────────────────────────────────────────────────
    # A bullish daily setup INSIDE a bearish higher-timeframe regime is a
    # counter-trend bounce, not a buy. A failed daily cycle AND a failed
    # investor cycle hard-caps it regardless of the regime score — a failed
    # cycle can produce a bounce, never an investment buy.
    bullish_tactical = state in ("FRESH BUY", "TURN SIGNALED")
    hard_fail = bool(cyc.get("failed_cycle") and cyc.get("ic_failed"))
    if bullish_tactical and (regime["regime"] == "bear" or hard_fail):
        inval = cyc.get("cand_price") or cyc.get("dcl_price")
        state = "COUNTERTREND BOUNCE"
        why = ("Short-term, a daily bottoming setup is forming — but the bigger picture is "
               "bearish (" + (regime["why"] or "weekly / investor timeframe pointing down")
               + "). A bounce here is COUNTER-TREND: daily-cycle lows that don't line up with "
                 "a weekly-cycle low tend to be left-translated and fail, then cascade toward "
                 "the larger cycle low — exactly the trap of buying a daily low in a falling "
                 "investor cycle."
               + (" The daily cycle has already failed (broke its own start low)."
                  if cyc.get("failed_cycle") else ""))
        why_zh = ("短期来看，正在形成日线筑底形态——但大局看空（"
                  + (regime["why"] or "weekly / investor timeframe pointing down")
                  + "）。此处的反弹属于逆势：与周线周期低点不对齐的日线周期低点往往"
                    "呈左移结构并最终失败，随后向更大周期低点蔓延——这正是在下行的"
                    "投资者周期中买入日线低点的陷阱。"
                  + ("日线周期已经失败（跌破其自身的起始低点）。"
                     if cyc.get("failed_cycle") else ""))
        nxt = ("Nimble traders only — small size, tight stop below "
               f"{inval}. Not an investment buy; wait for the weekly timeframe to actually "
               "turn up (or a fresh investor-cycle low to confirm) before trusting it.")
        nxt_zh = ("仅限灵活交易者——小仓位、将止损紧贴 "
                  f"{inval} 下方。并非投资性买入；在采信之前，请等待周线周期真正"
                  "转向上行（或出现新的投资者周期低点予以确认）。")

    score = LADDER_SCORE[state]
    if cyc.get("translation") == "left":
        score -= 10
        why += " Last cycle was left-translated (topped early) — a bearish structural tell."
        why_zh += " 上一周期为左移结构（见顶偏早）——属于看空的结构性信号。"
    if state in ("FRESH BUY", "RALLY ON") and cyc.get("translation") == "right":
        score += 5

    # pre-emptive (anticipatory) layer: enriches messaging in the watch states
    # without changing the calibrated state. A bullish early read in BOTTOM WATCH
    # nudges the score and re-frames the action toward "watch closely".
    early_note = ""
    early_note_zh = ""
    if early.get("dir") == "up" and state in ("BOTTOM WATCH", "TURN SIGNALED",
                                              "DECLINE", "COUNTERTREND BOUNCE"):
        score += 12 if early.get("tier") == "anticipated" else 6
        early_note = ("⚡ Early reversal building (" + early["tier"] + "): "
                      + "; ".join(early["signals"]) + ". These anticipate a low BEFORE "
                      "full confirmation — earlier entry, but a higher false-alarm rate, so "
                      "treat as a heads-up to watch closely, not a trigger yet.")
        early_note_zh = ("⚡ 反转正在提前酝酿（" + early["tier"] + "）："
                         + "; ".join(early["signals"]) + "。这些信号会在完全确认之前"
                         "预判低点——入场更早，但误报率更高，因此应视为密切关注的"
                         "提示，而非触发信号。")
    elif early.get("dir") == "down" and state in ("TOP WATCH", "RALLY ON"):
        score -= 12 if early.get("tier") == "anticipated" else 6
        early_note = ("⚡ Early topping signs (" + early["tier"] + "): "
                      + "; ".join(early["signals"]) + ". These anticipate a high BEFORE "
                      "confirmation — a heads-up to protect gains, not a sell trigger yet.")
        early_note_zh = ("⚡ 提前出现的做顶迹象（" + early["tier"] + "）："
                         + "; ".join(early["signals"]) + "。这些信号会在确认之前预判"
                         "高点——属于保护利润的提示，而非卖出触发信号。")

    disp = STATE_DISPLAY[state]
    plain = cycle_plain(cyc)
    entry = entry_timing(state, cyc, mtf)

    # ── Two-axis summary: TACTICAL (this daily state) vs REGIME (bigger picture),
    # plus how long the current move has been running ("ongoing" context).
    reg = regime["regime"]
    reg_word = REGIME_DISPLAY[reg]["word"]
    reg_word_zh = REGIME_DISPLAY[reg].get("word_zh", reg_word)
    reg_label_zh = REGIME_DISPLAY[reg].get("label_zh", REGIME_DISPLAY[reg]["label"])
    bits = []
    bits_zh = []
    if cyc.get("ic_week") is not None:
        bits.append(f"investor cycle week {cyc['ic_week']}")
        bits_zh.append(f"投资者周期第 {cyc['ic_week']} 周")
    if cyc.get("ic_failed"):
        bits.append("failed")
        bits_zh.append("已失败")
    if cyc.get("failed_age"):
        bits.append(f"daily cycle broke its start low {cyc['failed_age']}d ago")
        bits_zh.append(f"日线周期于 {cyc['failed_age']} 天前跌破其起始低点")
    elif cyc.get("dc_day") is not None:
        bits.append(f"daily cycle day {cyc['dc_day']}")
        bits_zh.append(f"日线周期第 {cyc['dc_day']} 天")
    dur = " · ".join(bits)
    dur_zh = " · ".join(bits_zh)
    regime_line = (f"Bigger picture: {REGIME_DISPLAY[reg]['label']}"
                   + (f" — {regime['why']}" if regime.get("why") else "")
                   + (f" ({dur})." if dur else "."))
    regime_line_zh = (f"大局：{reg_label_zh}"
                      + (f" — {regime['why']}" if regime.get("why") else "")
                      + (f"（{dur_zh}）。" if dur_zh else "。"))
    tactical_label = disp["label"]
    tactical_label_zh = disp.get("label_zh", tactical_label)
    summary_line = (f"Short-term (daily): {tactical_label.lower()}. "
                    f"Bigger picture ({reg_word}): {REGIME_DISPLAY[reg]['label'].lower()}.")
    summary_line_zh = (f"短期（日线）：{tactical_label_zh}。"
                       f"大局（{reg_word_zh}）：{reg_label_zh}。")

    # concise bullet points (the headline facts); full prose lives in `why`
    points = []
    points_zh = []
    points.append(f"Bigger picture is {REGIME_DISPLAY[reg]['label'].lower()} "
                  f"({reg_word} for a daily long)")
    points_zh.append(f"大局为{reg_label_zh}（对日线多头而言属{reg_word_zh}）")
    if cyc.get("failed_cycle"):
        age = f" ({cyc['failed_age']}d ago)" if cyc.get("failed_age") else ""
        age_zh = f"（{cyc['failed_age']} 天前）" if cyc.get("failed_age") else ""
        points.append(f"⚠ Failed cycle — price broke below the low that began this cycle{age}")
        points_zh.append(f"⚠ 失败周期——价格跌破了启动本周期的低点{age_zh}")
    if cyc.get("swing_low") or cyc.get("cand_swing"):
        points.append("Swing low printed (buyers rejected the low)")
        points_zh.append("摆动低点已现（买方拒绝了该低点）")
    points.append(("Back above" if cyc.get("above_ma10") else "Still below")
                  + " the 10-day average"
                  + (", and it's turning up" if cyc.get("ma10_rising") and cyc.get("above_ma10") else ""))
    points_zh.append(("重新站上" if cyc.get("above_ma10") else "仍位于")
                     + " 10 日均线"
                     + ("之上，且均线开始向上" if cyc.get("ma10_rising") and cyc.get("above_ma10")
                        else ("之上" if cyc.get("above_ma10") else "之下")))
    if d.get("macd_cross_up"):
        points.append("Daily momentum just crossed up")
        points_zh.append("日线动量刚刚向上交叉")
    elif d.get("macd_cross_dn"):
        points.append("Daily momentum just crossed down")
        points_zh.append("日线动量刚刚向下交叉")
    elif d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
        points.append(f"Daily momentum ~{d['macd_bars_to_cross']:.0f} bars from turning up")
        points_zh.append(f"日线动量距转为向上约 {d['macd_bars_to_cross']:.0f} 根 K 线")
    if plain.get("translation") and cyc.get("translation") == "left":
        points.append("Prior cycle topped early (a tiring-trend hint)")
        points_zh.append("上一周期见顶偏早（趋势走弱的暗示）")

    return {"state": state, "label": disp["label"], "action": disp["action"],
            "dir": disp["dir"], "score": int(np.clip(score, -100, 100)),
            "why": why, "next": nxt, "weekly_ok": weekly_ok,
            "regime": reg, "regime_label": REGIME_DISPLAY[reg]["label"],
            "regime_why": regime.get("why", ""), "regime_score": regime.get("score"),
            "regime_line": regime_line, "summary_line": summary_line,
            "points": points, "entry": entry, "cycle_plain": plain,
            "early_note": early_note,
            "early_tier": early.get("tier") if early_note else None,
            "early_dir": early.get("dir") if early_note else None,
            "why_zh": why_zh or why, "next_zh": nxt_zh or nxt,
            "regime_line_zh": regime_line_zh, "summary_line_zh": summary_line_zh,
            "points_zh": points_zh, "early_note_zh": early_note_zh}


def analyze(close: pd.Series, high: pd.Series | None = None,
            kind: str = "equity") -> dict:
    cyc = cycle_state(close, high, kind)
    mtf = mtf_snapshot(close, kind)
    early = early_signals(close, cyc, mtf)
    lad = ladder_state(cyc, mtf, early)
    return {"cycle": cyc, "mtf": mtf, "early": early, "ladder": lad}


# ------------------------------------------------------------- calibration ----

def calibrate_ladder(price_panel: dict[str, pd.Series], fwd: int = 21,
                     step: int = 5, dd_bad: float = -0.10) -> dict:
    """Per-state forward record by ladder state. price_panel: name -> close.
    Tracks BOTH endpoint return AND forward DRAWDOWN (max adverse excursion over
    the next `fwd` days) — the drawdown lens is the honest one for risk states
    (D43: avg return is U-shaped/misleading; the path matters), and is what
    actually quantifies a counter-trend-bounce knife-catch. Heavy-ish
    (re-evaluates state along history); cached to ladder_calibration.json."""
    # extra buckets isolate the pre-emptive layer's measured edge: the same
    # BOTTOM-WATCH context with vs without an early bullish read.
    extra = ["BOTTOM WATCH +early-bull", "BOTTOM WATCH no-early"]
    # each bucket holds (endpoint_return, forward_drawdown) pairs
    buckets: dict[str, list[tuple[float, float]]] = {s: [] for s in LADDER + extra}
    for name, close in price_panel.items():
        c = close.dropna()
        if len(c) < 600:
            continue
        fwd_ret = c.pct_change(fwd).shift(-fwd)
        cv = c.to_numpy()
        # walk weekly through history; a trailing 600-day window is all the
        # cycle/indicator math needs and keeps the walk-forward tractable
        for i in range(300, len(c) - fwd, step):
            sub = c.iloc[max(0, i - 600):i + 1]
            try:
                cyc = cycle_state(sub)
                mtf = {"D": _tf_state(sub),
                       "3D": _tf_state(sub.resample("3B").last().dropna()),
                       "W": _tf_state(sub.resample("W-FRI").last().dropna())}
                early = early_signals(sub, cyc, mtf)
                st = ladder_state(cyc, mtf, early)
            except Exception:  # noqa: BLE001
                continue
            if not st.get("state"):
                continue
            v = fwd_ret.iloc[i]
            if pd.isna(v):
                continue
            # forward max-drawdown = worst close-to-low over the next `fwd` days
            dd = float(cv[i + 1: i + 1 + fwd].min() / cv[i] - 1.0)
            rec = (float(v), dd)
            buckets[st["state"]].append(rec)
            if st["state"] == "BOTTOM WATCH":
                key = "BOTTOM WATCH +early-bull" if early.get("dir") == "up" \
                    else "BOTTOM WATCH no-early"
                buckets[key].append(rec)
    out = {}
    for s, vals in buckets.items():
        if len(vals) >= 40:
            a = np.array([r for r, _ in vals])
            dds = np.array([d for _, d in vals])
            out[s] = {"n": len(a), "hit_pct": round(100 * (a > 0).mean(), 1),
                      "avg_fwd_pct": round(100 * a.mean(), 2),
                      # drawdown lens: typical dip, bad-case (10th pctile) dip,
                      # and how often the next month draws down past dd_bad
                      "dd_med_pct": round(100 * float(np.median(dds)), 2),
                      "dd_p10_pct": round(100 * float(np.percentile(dds, 10)), 2),
                      "dd_bad_pct": round(100 * float((dds <= dd_bad).mean()), 1)}
    return out
