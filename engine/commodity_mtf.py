"""Multi-timeframe cycle-ladder + technical confluence for the Commodity Vector.

Ports the macro dashboard's MOMENTUM + TECHNICAL methodology (engine.cycles) into
the commodity page so each commodity is read with the SAME calibrated cycle-ladder
/ multi-timeframe engine the stock analyzer runs. On top of
cycles.analyze(close, high, kind="equity") it:
  * adds BIWEEKLY (2W) + MONTHLY (ME) technical timeframes (so D/3D/W/2W/ME),
  * derives a single CONFLUENCE VERDICT that reconciles a short-term bounce with
    the bigger-picture trend (the "counter-trend bounce vs investment buy"
    distinction) — and FUSES each commodity's own MEASURED calibration so the
    verdict honours per-asset polarity.

Two deliberate divergences from engine/btc_mtf.py (the Bitcoin Vector precedent):
  * kind="equity", not "crypto" — gold/silver/copper/oil trade on exchange
    calendars with 36-42 *trading*-day daily cycles (the equity preset), not the
    56-70 *calendar*-day crypto band. The long timeframes anchor on Friday
    (2W-FRI) to match the equity weekly bar (cycles.mtf_snapshot uses W-FRI).
  * confluence_verdict() folds this commodity's calibrated structural signals
    (driver axis + 12-month trend) into the bigger-picture governor,
    POLARITY-CORRECTED. So the verdict can never call an oil up-trend "bullish"
    (oil's 12-mo trend mean-reverts) or a supportive gold backdrop a buy (gold's
    driver is contrarian). The cycle-ladder timing TAPE stays asset-agnostic — it
    is the same calibrated equity engine, judged on timing/drawdown.

Recomputed each build, never persisted. Returns {} on any failure so a short or
broken series can't break the page build.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import cycles


def _long_timeframes(daily: pd.Series) -> dict:
    """Biweekly + monthly indicator states, identical shape to cycles._tf_state
    (so one UI loop renders all five). Friday-anchored 2W to match the equity
    W-FRI weekly bar. Needs >=600 daily bars for 2W (~40 biweekly bars), >=1200
    for ME (~57 monthly bars) so _tf_state's 40-bar floor is cleared."""
    out = {}
    if len(daily) > 600:
        out["2W"] = cycles._tf_state(daily.resample("2W-FRI").last().dropna())
    if len(daily) > 1200:
        out["ME"] = cycles._tf_state(daily.resample("ME").last().dropna())
    return out


def mtf_ladder(close: pd.Series, high: pd.Series | None = None) -> dict:
    """Full cycle-ladder + 5-timeframe MTF for one commodity (cycles.analyze on the
    EQUITY preset, augmented with 2W/ME). {} on any failure or too-short series
    (no usable cycle state)."""
    try:
        c = close.dropna()
        h = (high if high is not None else close).dropna()
        a = cycles.analyze(c, h, kind="equity")          # equity, NOT crypto
        if not a or not a.get("ladder"):
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


# Per-asset MEASURED calibration polarity. +1 = the signal reads with its raw sign;
# -1 = INVERTED (read contrarian); 0 = context-only (no directional vote). This is
# the honesty hinge: the bigger-picture governor counts each commodity's structural
# signals the way history says to read them.
#
# At runtime the polarity is DERIVED from the live calibration verdict
# (_verdict_polarity, via the calib_asset passed to confluence_verdict) so a weekly
# recalibration that flips a verdict updates the fusion automatically — no hardcoded
# drift. These module tables are only the FALLBACK when calibration is unavailable
# (first run / unit tests). They mirror the current data/commodity/calibration.json:
#   driver_score : energy/copper DIRECTIONAL (+), gold INVERTED (-),
#                  silver CONTEXT-ONLY (0). Added assets use conservative priors
#                  until their own calibration is written.
#   12-mo trend  : precious metals DIRECTIONAL (+), energy INVERTED (-),
#                  copper/grains CONTEXT (0).
_DRIVER_POLARITY = {
    "gold": -1, "silver": 0, "platinum": +1, "copper": +1,
    "oil": +1, "brent": +1, "natgas": 0,
    "corn": 0, "wheat": 0, "soybeans": 0,
}
_TREND_POLARITY = {
    "gold": +1, "silver": +1, "platinum": +1, "copper": 0,
    "oil": -1, "brent": -1, "natgas": -1,
    "corn": 0, "wheat": 0, "soybeans": 0,
}


def _verdict_polarity(verdict: str | None, fallback: int) -> int:
    """Map a MEASURED calibration verdict string to a directional polarity, using the
    SAME substring semantics as the dashboard's vbadge() badge. CONFIRMED /
    DIRECTIONAL = reads with its raw sign (+1); INVERTED = contrarian (-1);
    CONTEXT(-only) = no directional vote (0). Unknown/absent -> `fallback`."""
    if not verdict:
        return fallback
    v = verdict.upper()
    if "INVERTED" in v:
        return -1
    if "CONFIRMED" in v or "DIRECTIONAL" in v:
        return 1
    if "CONTEXT" in v:
        return 0
    return fallback

# Honest bilingual note when a structural signal is read against its raw sign, so
# the user sees WHY the bigger-picture vote may oppose the raw tape.
_CONTRARIAN_NOTE = {
    "oil": ("Oil's 12-month trend is read CONTRARIAN — oil mean-reverts, so a sustained "
            "up-trend leans bearish for forward returns and a washout leans bullish.",
            "原油的12个月趋势作逆向解读 — 原油均值回归，因此持续上涨趋势对未来收益偏空，"
            "而超卖洗盘偏多。"),
    "brent": ("Brent's 12-month trend is read CONTRARIAN by default — crude oil momentum "
              "often mean-reverts after supply-premium runs.",
              "布伦特的12个月趋势默认作逆向解读 — 原油供应溢价上涨后常均值回归。"),
    "natgas": ("Natural gas trend is read CONTRARIAN by default — weather/storage spikes "
               "are prone to sharp mean reversion.",
               "天然气趋势默认作逆向解读 — 天气/库存冲击后常急剧均值回归。"),
    "gold": ("Gold's macro driver is read CONTRARIAN — a supportive rates/dollar backdrop "
             "usually means gold has already run, while a headwind backdrop has tended to precede gains.",
             "黄金的宏观驱动作逆向解读 — 有利的利率/美元背景往往意味着黄金已经上涨，"
             "而逆风背景则曾领先上涨。"),
}


def _lean(value, polarity: int) -> int:
    """Polarity-corrected directional vote from a continuous score (NaN/0 -> 0)."""
    if value is None or polarity == 0:
        return 0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    if not np.isfinite(v) or v == 0:
        return 0
    return int(np.sign(v)) * polarity


# verdict prose, EN + ZH, keyed by (long_sign, short_sign) bucket — verbatim from
# engine/btc_mtf.py so a commodity reads the same way as BTC and the stock analyzer.
_VERDICTS = {
    "counter": ("Counter-trend bounce within a bearish bigger picture",
                "Short-term momentum is up, but the weekly/monthly trend and the cycle are down. "
                "High risk — nimble traders only, not an investment-grade buy.", "CAUTION",
                "在偏空大格局内的反弹", "短期动量向上，但周线/月线趋势与周期向下。高风险 — 仅适合灵活短线，"
                "并非适合投资的买入。", "谨慎"),
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


def confluence_verdict(a: dict, asset: str, sig_last: "pd.Series | None" = None,
                       calib_asset: dict | None = None) -> dict:
    """ONE verdict reconciling the timeframe contradiction, FUSED with this asset's
    measured calibration. Hierarchy: SHORT (daily/3d + the calibrated ladder tape)
    is the tape; LONG (monthly + cycle regime + cycle health + polarity-corrected
    driver/trend) is the governor. When they disagree it is NAMED a counter-trend
    move, not hidden.

    sig_last  : the last row of the commodity signals frame (df.iloc[-1]) — read for
                driver_score / ts_momentum / ts_trend.
    calib_asset: this asset's calibration sub-dict (reserved; polarity is encoded in
                the module tables, which mirror the same calibration verdicts)."""
    if not a:
        return {}
    mtf = a.get("mtf", {}) or {}
    ladder = a.get("ladder", {}) or {}
    cyc = a.get("cycle", {}) or {}

    # per-timeframe MACD-trend read (honest: shows whether each timeframe's TREND
    # has turned — a bounce can be up while every timeframe's MACD is still down).
    per_tf = {tf: ("up" if _tf_sign(mtf.get(tf)) > 0 else
                   ("down" if _tf_sign(mtf.get(tf)) < 0 else "flat"))
              for tf in ("D", "3D", "W", "2W", "ME")}
    mid_sign = int(np.sign(_tf_sign(mtf.get("W")) + _tf_sign(mtf.get("2W"))))

    reg = ladder.get("regime")
    state = ladder.get("state")

    # --- polarity-corrected structural leans from THIS commodity's MEASURED
    # calibration. Polarity DERIVES from the live calibration verdict (so a weekly
    # recalibration that flips a verdict updates the fusion automatically); the
    # module tables are only the fallback when calibration is absent. -------------
    def _g(k):
        if sig_last is None:
            return None
        try:
            return sig_last.get(k)
        except AttributeError:
            return None
    sigs = (calib_asset or {}).get("signals", {})
    driver_pol = _verdict_polarity(sigs.get("driver_score", {}).get("verdict"),
                                   _DRIVER_POLARITY.get(asset, 0))
    trend_pol = _verdict_polarity(sigs.get("ts_momentum", {}).get("verdict"),
                                  _TREND_POLARITY.get(asset, 0))
    driver_lean = _lean(_g("driver_score"), driver_pol)
    trend_val = _g("ts_momentum")
    if not pd.notna(trend_val):                      # catches BOTH None and NaN
        trend_val = {"up": 1.0, "down": -1.0}.get(_g("ts_trend"), 0.0)
    trend_lean = _lean(trend_val, trend_pol)

    # LONG = the structural governor (cycle regime + monthly trend + cycle health),
    # nudged by the asset's polarity-corrected macro/trend read.
    long_score = (2 if reg == "bull" else (-2 if reg == "bear" else 0)) + _tf_sign(mtf.get("ME"))
    if cyc.get("translation") == "left":
        long_score -= 1
    if cyc.get("failed_cycle"):
        long_score -= 1
    long_score += driver_lean + trend_lean
    long_sign = int(np.sign(long_score))

    # SHORT = the calibrated ladder tape (the same equity engine; asset-agnostic —
    # it detects the bounce the raw MACD signs miss, via swing-low + StochRSI pop).
    _bull_states = {"FRESH BUY", "TURN SIGNALED", "RALLY ON"}
    _bear_states = {"DECLINE", "ROLLING OVER", "TOP WATCH", "BOTTOM WATCH"}
    if state == "COUNTERTREND BOUNCE":
        short_sign = 1
    elif state in _bull_states:
        short_sign = 1
    elif state in _bear_states:
        short_sign = -1
    else:
        short_sign = int(np.sign(_tf_sign(mtf.get("D")) + _tf_sign(mtf.get("3D"))))

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
    head, sub, grade, head_zh, sub_zh, grade_zh = _VERDICTS[key]

    # when the calibrated ladder independently fired the counter-trend state, use
    # ITS verbatim entry text so the commodity reads like the stock analyzer.
    if state == "COUNTERTREND BOUNCE":
        et = ladder.get("entry", {}) or {}
        if et.get("text"):
            sub = et["text"]
            sub_zh = et.get("text_zh", sub_zh)

    # honest note when a structural signal was counted against its raw sign
    note, note_zh = "", ""
    if trend_lean != 0 and trend_pol < 0:
        note, note_zh = _CONTRARIAN_NOTE.get(asset, ("", ""))
    elif driver_lean != 0 and driver_pol < 0:
        note, note_zh = _CONTRARIAN_NOTE.get(asset, ("", ""))

    sd = cycles.STATE_DISPLAY.get(state, {})
    rd = cycles.REGIME_DISPLAY.get(reg, {})
    return {
        "headline": head, "headline_zh": head_zh, "sub": sub, "sub_zh": sub_zh,
        "grade": grade, "grade_zh": grade_zh,
        "short_sign": short_sign, "mid_sign": mid_sign, "long_sign": long_sign,
        "per_tf": per_tf, "ladder_state": state,
        "ladder_label": ladder.get("label") or sd.get("label"),
        "ladder_label_zh": sd.get("label_zh"),
        "ladder_action": ladder.get("action") or sd.get("action"),
        "ladder_action_zh": sd.get("action_zh"),
        "regime": reg, "regime_label": ladder.get("regime_label") or rd.get("label"),
        "regime_label_zh": rd.get("label_zh"),
        # commodity-specific honesty fields
        "driver_lean": driver_lean, "trend_lean": trend_lean,
        "calibrated_note": note, "calibrated_note_zh": note_zh,
    }
