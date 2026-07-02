"""Sector Confluence Engine — the validated multi-timeframe buy/sell setup signal
for the SPDR sector ETFs.

WHY IT EXISTS. The old sector tooling mis-timed entries: the "leaders" scorecard
called anything extended on the weekly oscillators "confirmed leadership" (so we
chased tops institutions were distributing into), and the heat board's 200-day
rotation lens confirmed turns weeks late and gave NO topping signal. This engine
replaces both with a single, backtested signal built from the SAME machinery the
stock library already runs (``engine.cycles``): a confluence of MACD + StochRSI
crossovers on the 3-day chart, with the DAILY chart as the early trigger and the
200-day as the knife gate.

WHAT WAS VALIDATED (1998-2026, 11 sector ETFs, point-in-time; forward 63d excess
vs SPY — research/SECTOR_CONFLUENCE.md, scripts/_bt_sector_confluence*.py):

  * BUY = a fresh up-turn (MACD up-cross / StochRSI up over 20 / approaching cross)
    ABOVE the 200-day and not yet extended (RSI<65). The SETUP — the days leading
    UP to the cross — carries the most edge (+0.65..0.73%); daily+3D agreement
    roughly doubles it (+0.87%). The same setup BELOW the 200-day loses (-0.18%) —
    so the 200-day trend gate is mandatory (separates buyable pullbacks from knives).
  * AVOID/SELL = EXTENDED (RSI>70 or StochRSI>80) AND rolling over. A confirmed
    3D down-cross from extended is the strongest avoid (-1.34%). A down-cross from
    a NON-extended state is a bounce trap (+0.29%), NOT a sell — so topping is
    gated on "extended", never on the bare down-cross.
  * The cross-sectional BUY-side minus AVOID-side spread is +0.83%/63d, monotone.

HONEST CEILING (carried onto the UI). Edges are modest, hit-rates ~50-54% (the
edge is in magnitude/tail, not the coin-flip), positive in 3/4 eras for buys and
negative in ALL 4 eras for the avoid. This is a RISK / ROTATION-TIMING map, not an
alpha machine and not a return forecast.

ADDITIVE / LEAF. Pure functions; reuses ``engine.cycles`` primitives. Missing or
thin inputs degrade to a NEUTRAL / ``None`` read, never raise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cycles import macd_parts, stoch_rsi
from engine.technicals import rsi

# 3-business-day bar = the user's "3-day chart" (equity preset, engine.cycles).
TF3 = "3B"
_BUY_RSI_GATE = 65.0      # don't call something already extended a fresh "buy"
_EXT_RSI = 70.0           # extended / "late" thresholds (overbought)
_EXT_STOCH = 80.0
_OS_STOCH = 20.0          # StochRSI oversold line the user keys bottoms off

# Oversold-bounce (tactical mean-reversion) carve-out — see the OVERSOLD_BOUNCE
# state below and research/SECTOR_CONFLUENCE.md. Restricted to the four low-vol
# DEFENSIVE sectors that an independent variance-ratio / OU-half-life test confirmed
# are genuinely range-bound (oscillate around trend) rather than trending — so a
# below-200d oversold dip is a buyable bounce, not a falling knife. Cyclicals are
# deliberately excluded (their below-200d guarded tail is still ~-24%).
_OVERSOLD_BOUNCE_COHORT = {"XLU", "XLP", "XLV", "XLRE"}
_OSB_MAX_DEPTH = -0.12    # don't fire deeper than 12% below the 200-day (knife cap)

# Measured per-state base rates (forward 63d excess vs SPY, %, hit-rate, n) from
# the FULL state machine, weekly-sampled across the 11 sector ETFs 1998-2026
# (``calibrate`` output — research/SECTOR_CONFLUENCE.md). Static fallback; the
# build refreshes these live so the displayed numbers always match the live rule.
# Note the honest nuance: the negative avoid-edge concentrates in TOPPING/SELL —
# a pure EXTENDED (overbought but still rising) is ~market-neutral at 63d, i.e.
# "late, don't chase" rather than "short it".
# Each entry carries BOTH the forward-63d EXCESS-vs-SPY (the rotation metric the
# buy/avoid states are sorted on) AND the ABSOLUTE forward-63d return. The dual is
# the honesty layer for OVERSOLD_BOUNCE: that state is positive ABSOLUTE (the dip
# bounces) but ~flat/negative EXCESS (it lags a rising SPY) — so absolute is its
# headline and excess is shown as the "lags SPY" cost. Refreshed live by calibrate.
STATE_BASE_RATES = {
    "BUY":            {"exc63": 1.10, "hit": 56, "abs63": 3.70, "abs_hit": 72, "n": 199},
    "BUY_PARTIAL":    {"exc63": 0.40, "hit": 50, "abs63": 2.25, "abs_hit": 65, "n": 1281},
    "SETUP_BUY":      {"exc63": 0.32, "hit": 52, "abs63": 3.13, "abs_hit": 71, "n": 486},
    "NEUTRAL":        {"exc63": 0.08, "hit": 50, "abs63": 2.72, "abs_hit": 67, "n": 2547},
    "EXTENDED":       {"exc63": 0.06, "hit": 50, "abs63": 2.52, "abs_hit": 68, "n": 2185},
    "TOPPING":        {"exc63": -0.11, "hit": 48, "abs63": 2.10, "abs_hit": 67, "n": 2335},
    "SELL":           {"exc63": -1.24, "hit": 40, "abs63": -0.05, "abs_hit": 59, "n": 169},
    "BELOW_TREND":    {"exc63": -0.16, "hit": 49, "abs63": 2.45, "abs_hit": 64, "n": 3477},
    "OVERSOLD_BOUNCE": {"exc63": 0.29, "hit": 55, "abs63": 3.98, "abs_hit": 79, "n": 136},
}

# Display metadata per state: side, human label (EN/中文), one-line action, a UI
# colour var, conviction emoji prefix, and a coarse sort priority (most actionable
# entries first, then neutral, then the avoid family, then below-trend).
_STATE_META = {
    "BUY":         ("buy", "BUY", "买入", "Fresh up-turn confirmed on the daily AND 3-day — entry open.",
                    "日线与3日线同时确认转上——入场窗口打开。", "var(--up)", 1),
    "BUY_PARTIAL": ("buy", "BUY", "买入", "One timeframe has turned up above trend — entry forming.",
                    "一个时间框架已转上且在趋势之上——入场构筑中。", "var(--up)", 2),
    "SETUP_BUY":   ("buy", "SETUP", "预备", "Approaching an up-cross above trend — get ready, not yet triggered.",
                    "在趋势之上接近上穿——准备，尚未触发。", "var(--info)", 3),
    "NEUTRAL":     ("neutral", "NEUTRAL", "中性", "In trend, nothing fresh — no edge either way.",
                    "处于趋势中，无新信号——两边都无优势。", "var(--muted)", 5),
    "EXTENDED":    ("avoid", "EXTENDED", "过热", "Overbought and still rising — late; hold/trim, don't chase.",
                    "超买且仍在上行——已晚；持有/减仓，勿追。", "var(--orange)", 7),
    "TOPPING":     ("avoid", "TOPPING", "见顶", "Overbought and rolling over — distribution risk; reduce.",
                    "超买且开始回落——派发风险；减仓。", "var(--down)", 8),
    "SELL":        ("avoid", "SELL", "卖出", "Overbought with a confirmed 3-day down-cross — exit/avoid.",
                    "超买且3日线确认下穿——离场/回避。", "var(--down)", 9),
    "BELOW_TREND": ("avoid", "BELOW TREND", "趋势下方", "Below the 200-day — bottoming buys here are knives; wait for a reclaim.",
                    "处于200日线下方——此处抄底如接飞刀；等待收复。", "var(--muted)", 10),
    # tactical mean-reversion dip — NOT a confirmed buy (own 'tactical' side so it
    # never enters the buy/avoid counts or the rotation spread). Surfaced so the
    # range-bound defensives stop being buried in BELOW_TREND.
    "OVERSOLD_BOUNCE": ("tactical", "OVERSOLD BOUNCE", "超卖反弹",
                    "Below the 200-day but a range-bound defensive, oversold and turning up with the Fed put intact — "
                    "a tactical mean-reversion bounce (positive in ABSOLUTE terms, ~+4%/63d, hit ~79%; roughly "
                    "market-neutral vs SPY and prone to lag in a strong bull tape). A dip-trade, not a confirmed "
                    "trend buy — size small, set a stop.",
                    "处于200日线下方，但属区间震荡的防御板块，已超卖并转上、且美联储托底仍在——"
                    "战术性均值回归反弹（绝对收益为正，约+4%/63日，胜率约79%；相对SPY大致持平，强势牛市中易跑输）。"
                    "这是抄反弹，并非确认的趋势买入——小仓位并设止损。", "var(--info)", 6),
}

# Conviction tier labels (count of agreeing legs).
_CONVICTION = {3: ("full confluence", "全共振"), 2: ("partial", "部分"),
               1: ("setup", "预备"), 0: ("—", "—")}


def _last(s: pd.Series, default=np.nan):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else default


def _flag_frame(close: pd.Series) -> pd.DataFrame:
    """Vectorised MACD/StochRSI/RSI cross + setup flags for one (already-resampled)
    close series. Definitions match the backtest AND ``engine.cycles._tf_state``:
      * macd_up/dn  = histogram >0/<0 now having crossed zero within the last 3 bars
      * stoch_up/dn = StochRSI ≥20 (from <20) / ≤80 (from >80) within the last 3 bars
      * setup_up/dn = histogram rising/falling 3 bars while still on the wrong side
      * stoch_roll / rsi_roll = the EARLY topping tell (momentum turning down out of
        overbought) — fires before the confirmed cross."""
    m = macd_parts(close)
    h = m["hist"]
    s = stoch_rsi(close)
    r = rsi(close, 14)
    prior_le0 = (h.shift(1) <= 0) | (h.shift(2) <= 0) | (h.shift(3) <= 0)
    prior_ge0 = (h.shift(1) >= 0) | (h.shift(2) >= 0) | (h.shift(3) >= 0)
    prior_s_lt20 = (s.shift(1) < _OS_STOCH) | (s.shift(2) < _OS_STOCH) | (s.shift(3) < _OS_STOCH)
    prior_s_gt80 = (s.shift(1) > _EXT_STOCH) | (s.shift(2) > _EXT_STOCH) | (s.shift(3) > _EXT_STOCH)
    rising = (h > h.shift(1)) & (h.shift(1) > h.shift(2))
    falling = (h < h.shift(1)) & (h.shift(1) < h.shift(2))
    stoch_roll = (s < s.shift(1)) & ((s.shift(1) > _EXT_STOCH) | (s.shift(2) > _EXT_STOCH))
    rsi_roll = (r < r.shift(1)) & ((r.shift(1) > _EXT_RSI) | (r.shift(2) > _EXT_RSI))
    return pd.DataFrame({
        "hist": h, "stoch": s, "rsi": r,
        "macd_up": (h > 0) & prior_le0, "macd_dn": (h < 0) & prior_ge0,
        "stoch_up": (s >= _OS_STOCH) & prior_s_lt20, "stoch_dn": (s <= _EXT_STOCH) & prior_s_gt80,
        "setup_up": (h < 0) & rising, "setup_dn": (h > 0) & falling,
        "stoch_roll": stoch_roll, "rsi_roll": rsi_roll,
    }).fillna(False)


def _approach_eta_days(close: pd.Series, bar_days: int) -> int | None:
    """Bars-to-zero-cross from the current 3-bar histogram slope, in trading days
    (mirrors engine.cycles._tf_state, capped at 6 bars)."""
    h = macd_parts(close)["hist"].dropna()
    if len(h) < 4:
        return None
    slope = (h.iloc[-1] - h.iloc[-4]) / 3
    if h.iloc[-1] < 0 and h.iloc[-1] > h.iloc[-2] > h.iloc[-3] and slope > 0:
        eta = -h.iloc[-1] / slope
    elif h.iloc[-1] > 0 and h.iloc[-1] < h.iloc[-2] < h.iloc[-3] and slope < 0:
        eta = h.iloc[-1] / -slope
    else:
        return None
    if eta > 6:
        return None
    return int(round(max(eta, 0.5) * bar_days))


def _verdict(d: pd.Series, t3: pd.Series, above200: bool, above50: bool, *,
             depth200: float | None = None, slope200_up: bool = False,
             osb_eligible: bool = False) -> dict:
    """The validated state machine over the latest daily (d) + 3-day (t3) flags.

    The below-200d branch is a falling-knife BY DEFAULT (the keyword guards default
    off, so a bare call stays a knife). It is only carved into the tactical
    OVERSOLD_BOUNCE state when the caller asserts ``osb_eligible`` (the range-bound
    defensive cohort, Fed-put present — enforced in sector_signal/board) AND the
    price shape is a shallow, turning oversold dip rather than a deep collapse:
    ``depth200`` (price/200d - 1) shallower than -12% and the 200-day not falling."""
    ext_3d = (t3["rsi"] > _EXT_RSI) or (t3["stoch"] > _EXT_STOCH)
    ext_d = (d["rsi"] > _EXT_RSI) or (d["stoch"] > _EXT_STOCH)
    extended = ext_3d or ext_d

    fresh_up_3d = bool(t3["macd_up"] or t3["stoch_up"])
    fresh_up_d = bool(d["macd_up"] or d["stoch_up"])
    setup_up = bool(t3["setup_up"] or d["setup_up"])
    down_cross_3d = bool(t3["macd_dn"] or t3["stoch_dn"])
    rolling = bool(t3["setup_dn"] or d["setup_dn"] or d["stoch_roll"] or d["rsi_roll"])

    # conviction = count of agreeing legs among {daily, 3D-MACD, 3D-Stoch}
    up_legs = int(fresh_up_d or d["setup_up"]) + int(t3["macd_up"] or t3["setup_up"]) + int(t3["stoch_up"])
    dn_legs = int(ext_d) + int(t3["macd_dn"]) + int(t3["stoch_dn"] or t3["setup_dn"])

    if not above200:
        # tactical oversold-bounce carve-out (literal StochRSI cross-up<20 = signal-A;
        # the reclaim-filtered variant failed the within-regime permutation test).
        osb = bool(t3["stoch_up"] or d["stoch_up"])
        if (osb_eligible and osb and depth200 is not None
                and depth200 > _OSB_MAX_DEPTH and slope200_up):
            return {"state": "OVERSOLD_BOUNCE", "conviction": 1,
                    "reason": "below 200d but an oversold, turning, range-bound defensive dip"}
        return {"state": "BELOW_TREND", "conviction": 1, "reason": "price below the 200-day"}

    # --- avoid side takes priority once extended (don't let stray up-noise mask a top)
    if extended and down_cross_3d:
        return {"state": "SELL", "conviction": max(dn_legs, 2), "reason": "extended + confirmed 3D down-cross"}
    if extended and rolling:
        return {"state": "TOPPING", "conviction": max(dn_legs, 1), "reason": "extended + momentum rolling over"}
    if extended:
        return {"state": "EXTENDED", "conviction": 1, "reason": "overbought, still rising"}

    # --- buy side (only when NOT extended and the 3D isn't already hot)
    if t3["rsi"] < _BUY_RSI_GATE:
        if fresh_up_3d and fresh_up_d:
            return {"state": "BUY", "conviction": 3, "reason": "daily + 3D fresh up-turn"}
        if fresh_up_3d or fresh_up_d:
            return {"state": "BUY_PARTIAL", "conviction": max(up_legs, 2), "reason": "one timeframe turned up"}
        if setup_up:
            return {"state": "SETUP_BUY", "conviction": 1, "reason": "approaching an up-cross"}
    return {"state": "NEUTRAL", "conviction": 0, "reason": "in trend, nothing fresh"}


def _weekly_riding_override(state: str, weekly_fresh_up: bool, weekly_not_hot: bool) -> dict | None:
    """WEEKLY-CROSS coherence carve-out. An EXTENDED (overbought-still-rising) read is NOT a
    "don't chase" top when the WEEKLY (investor) cycle has JUST turned up and isn't itself
    overbought — that is early in a fresh up-leg. Returns the display override that relabels it
    RIDING so this panel AGREES with the cycles-ladder's RALLY ON (the XLV 2026-06 case); the
    caller keeps the state KEY = EXTENDED so the measured base rate is unchanged. None = no override.
    Mirrors engine.cycles' weekly-cross veto and engine.sector_cycles._classify_phase."""
    if state == "EXTENDED" and weekly_fresh_up and weekly_not_hot:
        return {"side": "neutral", "color": "var(--link)", "label_en": "RIDING", "label_zh": "顺势",
                "act_en": ("Overbought, but the weekly (investor) cycle just turned up — early in a "
                           "new up-leg, so hold / add on dips, not a top."),
                "act_zh": ("虽已超买，但周线（投资者）周期刚刚向上转向——处于新上行段早期，"
                           "因此应持有／回调加仓，而非见顶。"),
                "reason": "overbought but the weekly investor cycle just turned up — early in a new up-leg"}
    return None


def sector_signal(close: pd.Series, name: str | None = None,
                  spy_close: pd.Series | None = None, ticker: str | None = None,
                  put_absent: bool = False) -> dict:
    """The validated confluence read for one sector ETF close series. PURE.

    Returns the verdict state, conviction, the daily + 3-day oscillator snapshot,
    the trend gate, an approaching-cross ETA (days), and the measured base rate for
    the state. Thin history (<~260 daily bars) degrades to a NEUTRAL stub.

    ``ticker`` + ``put_absent`` gate the tactical OVERSOLD_BOUNCE carve-out: it can
    only fire for the range-bound defensive cohort with the Fed put PRESENT (in a
    put-absent regime even these dips kept falling — 2000/08/22)."""
    c = close.dropna()
    out = {"ticker": ticker, "name": name, "state": "NEUTRAL", "conviction": 0,
           "ok": False}
    if len(c) < 260:
        return out
    c3 = c.resample(TF3).last().dropna()
    if len(c3) < 40:
        return out
    df = _flag_frame(c)
    df3 = _flag_frame(c3)
    d, t3 = df.iloc[-1], df3.iloc[-1]
    # weekly (investor-cycle) context — the DOMINANT clock the daily/3-day reads live inside.
    # A daily/3-day "overbought" print is NOT a top early in a fresh weekly up-leg.
    cW = c.resample("W-FRI").last().dropna()
    wk = _flag_frame(cW).iloc[-1] if len(cW) >= 30 else None
    weekly_fresh_up = bool(wk is not None and wk["macd_up"])
    weekly_not_hot = bool(wk is None or pd.isna(wk["rsi"]) or wk["rsi"] < _EXT_RSI)
    sma200_series = c.rolling(200).mean()
    sma200 = float(sma200_series.iloc[-1])
    sma50 = float(c.iloc[-50:].mean())
    px = float(c.iloc[-1])
    above200, above50 = px > sma200, px > sma50
    # oversold-bounce guards: shallow depth + 200-day not falling (21-bar slope),
    # cohort + Fed-put-present eligibility (the load-bearing knife guards)
    depth200 = (px / sma200 - 1) if sma200 else None
    slope200_up = bool(len(sma200_series.dropna()) >= 22
                       and sma200_series.iloc[-1] - sma200_series.iloc[-22] >= 0)
    osb_eligible = (ticker in _OVERSOLD_BOUNCE_COHORT) and not put_absent

    v = _verdict(d, t3, above200, above50, depth200=depth200,
                 slope200_up=slope200_up, osb_eligible=osb_eligible)
    state = v["state"]
    side, label_en, label_zh, act_en, act_zh, color, prio = _STATE_META[state]
    _ov = _weekly_riding_override(state, weekly_fresh_up, weekly_not_hot)
    early_weekly_leg = _ov is not None
    if _ov:
        side, color = _ov["side"], _ov["color"]
        label_en, label_zh = _ov["label_en"], _ov["label_zh"]
        act_en, act_zh = _ov["act_en"], _ov["act_zh"]
        v["reason"] = _ov["reason"]
    conv = int(v["conviction"])
    conv_en, conv_zh = _CONVICTION.get(min(conv, 3), _CONVICTION[0])

    # approaching-cross ETA on the 3D for SETUP states (and as context elsewhere)
    eta = _approach_eta_days(c3, 3)

    rs60 = None
    if spy_close is not None:
        rel = (c / spy_close.reindex(c.index)).dropna()
        if len(rel) > 63:
            rs60 = round(float(rel.iloc[-1] / rel.iloc[-63] - 1) * 100, 1)

    out.update({
        "name": name, "ok": True, "price": round(px, 2),
        "state": state, "side": side, "priority": prio, "early_weekly_leg": early_weekly_leg,
        "label": label_en, "label_zh": label_zh,
        "action": act_en, "action_zh": act_zh, "color": color,
        "conviction": conv, "conviction_label": conv_en, "conviction_label_zh": conv_zh,
        "above200": above200, "above50": above50,
        "rsi_3d": round(float(t3["rsi"]), 0) if pd.notna(t3["rsi"]) else None,
        "stoch_3d": round(float(t3["stoch"]), 0) if pd.notna(t3["stoch"]) else None,
        "rsi_d": round(float(d["rsi"]), 0) if pd.notna(d["rsi"]) else None,
        "stoch_d": round(float(d["stoch"]), 0) if pd.notna(d["stoch"]) else None,
        "days_to_cross": eta,
        "rs_60d": rs60,
        "reason": v["reason"],
        "base_rate": STATE_BASE_RATES.get(state),
        # the raw 3D + daily cross flags, for a precise "what fired" line
        "flags": {
            "macd_up_3d": bool(t3["macd_up"]), "stoch_up_3d": bool(t3["stoch_up"]),
            "macd_dn_3d": bool(t3["macd_dn"]), "stoch_dn_3d": bool(t3["stoch_dn"]),
            "setup_up_3d": bool(t3["setup_up"]), "setup_dn_3d": bool(t3["setup_dn"]),
            "macd_up_d": bool(d["macd_up"]), "stoch_up_d": bool(d["stoch_up"]),
            "macd_dn_d": bool(d["macd_dn"]), "stoch_dn_d": bool(d["stoch_dn"]),
            "stoch_roll_d": bool(d["stoch_roll"]), "rsi_roll_d": bool(d["rsi_roll"]),
        },
    })
    return out


def signal_line(sig: dict, zh: bool = False) -> str:
    """A compact 'what fired' phrase for the 3-day signal column."""
    f = sig.get("flags") or {}
    bits = []
    pair = [("macd_up_3d", "MACD ↑", "MACD 上穿"), ("stoch_up_3d", "StochRSI ↑20", "StochRSI 上穿20"),
            ("macd_dn_3d", "MACD ↓", "MACD 下穿"), ("stoch_dn_3d", "StochRSI ↓80", "StochRSI 跌破80"),
            ("setup_up_3d", "MACD curling up", "MACD 上弯"), ("setup_dn_3d", "MACD rolling down", "MACD 下弯")]
    for k, en, zhk in pair:
        if f.get(k):
            bits.append(zhk if zh else en)
    if not bits:
        # fall back to the daily early tell
        if f.get("stoch_roll_d") or f.get("rsi_roll_d"):
            bits.append("daily momentum rolling down" if not zh else "日线动量回落")
        elif f.get("macd_up_d") or f.get("stoch_up_d"):
            bits.append("daily turning up" if not zh else "日线转上")
    eta = sig.get("days_to_cross")
    if eta and not any(f.get(k) for k in ("macd_up_3d", "macd_dn_3d")):
        bits.append((f"~{eta}d to cross" if not zh else f"约{eta}天后交叉"))
    return ", ".join(bits) if bits else ("no fresh cross" if not zh else "无新交叉")


def board(closes: pd.DataFrame, names: dict[str, str], sectors: list[str],
          spy: pd.Series | None = None, put_absent: bool = False) -> dict:
    """Assemble the per-sector reads into the Sector Confluence board payload.

    Rows sorted by actionable priority (BUY/SETUP first, then NEUTRAL, then the
    EXTENDED/TOPPING/SELL avoid family, then BELOW-TREND), ties broken by conviction.
    ``put_absent`` (the index Fed-put gate) hardens the BELOW-TREND caveat. PURE."""
    rows = []
    for t in sectors:
        if t not in closes.columns:
            continue
        sig = sector_signal(closes[t], names.get(t, t), spy_close=spy,
                            ticker=t, put_absent=put_absent)
        if not sig.get("ok"):
            continue
        sig["ticker"] = t
        if sig["state"] == "BELOW_TREND" and put_absent:
            sig["action"] = ("Below the 200-day with the Fed put ABSENT — the 2000/08/22 "
                             "regime where washouts kept falling. Stand aside.")
            sig["action_zh"] = "200日线下方且美联储托底缺位——即2000/08/22年错杀续跌的格局。观望。"
        rows.append(sig)
    rows.sort(key=lambda r: (r["priority"], -r["conviction"],
                             -(r.get("rs_60d") if r.get("rs_60d") is not None else 0)))
    buys = [r for r in rows if r["side"] == "buy"]
    avoids = [r for r in rows if r["side"] == "avoid"]
    tactical = [r for r in rows if r["side"] == "tactical"]
    return {
        "sectors": rows,
        "n_buy": len(buys), "n_avoid": len(avoids), "n_tactical": len(tactical),
        "buy_tickers": [r["ticker"] for r in buys],
        "avoid_tickers": [r["ticker"] for r in avoids],
        "tactical_tickers": [r["ticker"] for r in tactical],
        "put_absent": bool(put_absent),
        "evidence": ("Confluence of MACD + StochRSI crossovers on the 3-day chart "
                     "(daily as early trigger), 200-day trend-gated; extended = avoid. "
                     "Validated 1998-2026, research/SECTOR_CONFLUENCE.md. Risk/timing "
                     "map, not a return forecast."),
    }


# ------------------------------------------------------------- calibration ----

def calibrate(closes: pd.DataFrame, sectors: list[str], spy: pd.Series,
              horizon: int = 63) -> dict:
    """Measure each state's forward ``horizon``-day return across history (weekly-
    sampled, point-in-time) so the UI shows MEASURED base rates — BOTH excess-vs-SPY
    and ABSOLUTE. Mirrors engine.technicals.calibrate's honesty pattern. Returns
    {state -> {exc63, hit, abs63, abs_hit, n}}.

    Point-in-time: the 3-day flags are computed on the resampled series and
    forward-filled onto daily dates, so the read on date t uses only data ≤ t. Forward
    returns use a NEXT-BAR fill (W1c, audit #15): the state read on bar t is entered on
    t+1's close, so the measured base rate is not flattered by same-bar entry (the honest
    convention shared with engine.grading / validation.py). The
    OVERSOLD_BOUNCE state is measured over the cohort's full below-200d history
    (cohort + price-shape guards, the SAME _verdict); the live state additionally
    requires the Fed put PRESENT, so the live read is conservative vs this rate."""
    from collections import defaultdict
    acc_exc: dict[str, list[float]] = defaultdict(list)
    acc_abs: dict[str, list[float]] = defaultdict(list)
    spy = spy.dropna()
    for t in sectors:
        if t not in closes.columns:
            continue
        c = closes[t].dropna()
        if len(c) < 400:
            continue
        c3 = c.resample(TF3).last().dropna()
        df = _flag_frame(c)
        df3 = _flag_frame(c3).reindex(c.index, method="ffill")
        sma200 = c.rolling(200).mean()
        # NEXT-BAR fill (W1c, audit #15): the state is READ on bar i but the position is
        # FILLED on bar i+1 (you cannot trade the same close you observe the signal on),
        # matching engine.grading / validation.py's alloc.shift(1). Denominator = c.shift(-1)
        # (the next close), numerator = c.shift(-horizon-1) (horizon bars past the fill), both
        # read at i via .iloc[i]. The SPY benchmark fills on the SAME next bar for consistency.
        spy_c = spy.reindex(c.index)
        fwd = c.shift(-horizon - 1) / c.shift(-1) - 1
        spy_fwd = spy_c.shift(-horizon - 1) / spy_c.shift(-1) - 1
        exc = (fwd - spy_fwd)
        osb_elig = t in _OVERSOLD_BOUNCE_COHORT
        # -horizon-1: next-bar fill needs ONE extra forward bar (fill at i+1, measure to i+1+horizon)
        for i in range(200, len(c) - horizon - 1, 5):     # weekly sample
            if not np.isfinite(exc.iloc[i]):
                continue
            d, t3 = df.iloc[i], df3.iloc[i]
            if not np.isfinite(t3.get("rsi", np.nan)):
                continue
            s2 = sma200.iloc[i]
            above = bool(c.iloc[i] > s2) if np.isfinite(s2) else True
            depth_i = (c.iloc[i] / s2 - 1) if np.isfinite(s2) and s2 else None
            slope_i = bool(i >= 221 and np.isfinite(sma200.iloc[i - 21])
                           and s2 - sma200.iloc[i - 21] >= 0)
            v = _verdict(d, t3, above, True, depth200=depth_i,
                         slope200_up=slope_i, osb_eligible=osb_elig)
            acc_exc[v["state"]].append(float(exc.iloc[i]))
            acc_abs[v["state"]].append(float(fwd.iloc[i]))
    out = {}
    for st, vals in acc_exc.items():
        if len(vals) >= 50:
            a = np.array(vals)
            b = np.array(acc_abs[st])
            out[st] = {"exc63": round(float(100 * a.mean()), 2),
                       "hit": int(round(100 * (a > 0).mean())),
                       "abs63": round(float(100 * b.mean()), 2),
                       "abs_hit": int(round(100 * (b > 0).mean())), "n": len(a)}
    return out
