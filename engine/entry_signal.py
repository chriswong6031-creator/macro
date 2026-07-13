"""Entry-timing gauge (engine v2) — the SECOND, separate gauge.

The conviction score answers "is this a name worth OWNING?". This module answers
the orthogonal question the old engine conflated into it: "should I buy it NOW, and
if not, at what PRICE and WHEN?". It turns the cycle/ladder read into a structured,
actionable plan — a status, a buy zone (real prices), a don't-chase line, an
invalidation stop, a rough timing window, and an entry-favorability read by horizon —
so a high-conviction-but-extended leader (HWM, NVDA) reads "WAIT — accumulate ~$X on
the pullback", never "99 · Buy Now".

It is deliberately downstream of and consistent with engine.cycles: it READS the
already-calibrated ladder state + entry urgency + the drawdown-calibrated
`eq_score` + multi-timeframe `bottom_confidence`, and adds the price levels and the
horizon read the cards/Mastermind need. It never re-decides direction — the ladder
owns that. Display + decision context; the cycle-top veto lives in engine.cycles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ladder entry.urgency -> coarse entry STATUS (the headline state of the gauge)
# now/imminent are buyable; the rest are wait/avoid with a price plan attached.
_STATUS_BY_URGENCY = {
    "now": "buy_now",          # FRESH BUY — window open
    "imminent": "buy_soon",    # setup almost complete / on confirmation
    "soon": "watch",           # a low is approaching — don't front-run
    "later": "wait_pullback",  # mid-cycle dip; real low not due yet
    "hold": "hold",            # trend intact, late — don't add, hold
    "caution": "extended",     # stretched / don't-chase / take-profits
    "exit": "exit",            # rolling over — reduce
    "avoid": "avoid",          # downtrend — stand aside
}

_HEADLINE = {
    "buy_now":       ("Buy zone — entry open now", "买入区 — 入场窗口已开启"),
    "partial":       ("Partial entry — half size now", "部分入场 — 当前可建半仓"),
    # the daily-cycle ladder turned up but the validated MACD-2D x StochRSI-3D confluence has
    # NOT fired yet — an honest wait state so the card never claims the window is open early.
    "await_confluence": ("Cycle turn — awaiting confluence cross", "周期拐点 — 等待共振交叉确认"),
    "buy_soon":      ("Buy soon — on confirmation", "即将买入 — 待确认"),
    "watch":         ("Watch — a low is approaching", "观察 — 低点临近"),
    "wait_pullback": ("Wait for the pullback", "等待回撤"),
    "hold":          ("Hold — don't add here", "持有 — 此处不宜加仓"),
    "extended":      ("Extended — wait for a pullback", "过度拉伸 — 等待回撤"),
    # a regime-gate COUNTERTREND BOUNCE carries urgency 'caution' meaning "the turn is
    # NOT confirmed" — often a washed-out name far BELOW trend, the opposite of extended.
    "bounce_wait":   ("Bounce — turn not confirmed; wait", "反弹 — 转向未确认，先观望"),
    "topping":       ("Topping — protect gains", "见顶 — 保护利润"),
    "exit":          ("Exit / reduce — rolling over", "离场/减仓 — 掉头向下"),
    "avoid":         ("Avoid — downtrend", "回避 — 下行趋势"),
    "blocked":       ("Blocked — failed cycle", "受阻 — 失败周期"),
}

# urgency -> a coarse 0-3 "act now" gauge for the UI ring (3 = act, 0 = stand aside)
_ACT_LEVEL = {"now": 3, "imminent": 2, "soon": 1, "later": 1, "hold": 1,
              "caution": 0, "exit": 0, "avoid": 0}


def _atr_pct(close: pd.Series, high: pd.Series | None, n: int = 14) -> float | None:
    """Average true range as a % of price. Uses high/low ranges when available,
    else a close-to-close move proxy — robust for sizing the buy zone width."""
    c = close.dropna()
    if len(c) < n + 2:
        return None
    if high is not None:
        h = high.reindex(c.index)
        # low not threaded through the library for breadth names — approximate the
        # bar low as min(close, high-of-prev-range) is unreliable, so fall back to
        # close-to-close when low is absent. We only have high here, so use c2c.
    tr = c.pct_change().abs()
    atr = float(tr.tail(n).mean())
    return round(100 * atr, 2) if np.isfinite(atr) else None


def _ma(close: pd.Series, n: int) -> float | None:
    c = close.dropna()
    if len(c) < n:
        return None
    return float(c.tail(n).mean())


def _round_px(x: float | None) -> float | None:
    if x is None or not np.isfinite(x):
        return None
    if x >= 100:
        return round(x, 1)
    if x >= 1:
        return round(x, 2)
    return round(x, 4)


def _clip1(x: float) -> float:
    return float(np.clip(x, -1.0, 1.0))


def _horizon_read(rec: dict, eq_score: float | None, spot: float,
                  ma50: float | None, ma200: float | None,
                  dc_day: int | None, band: tuple) -> dict:
    """Entry-favorability by horizon, each in [-1, +1] (higher = better entry NOW
    for that horizon). d3 = near-term timing (drawdown-calibrated eq), d21 = swing
    (eq + trend + where we are in the cycle), d63 = position (primary trend + how
    extended). These are entry-QUALITY reads, NOT return forecasts."""
    tech = rec.get("tech") or {}
    pv200 = tech.get("pct_vs_200dma")
    pv50 = tech.get("pct_vs_50dma")
    # near term: the signed, drawdown-calibrated entry quality
    d3 = _clip1((eq_score or 0) / 100.0)
    # swing: blend eq with trend-with-it and cycle freshness
    trend_up = 0.0
    if ma50 is not None:
        trend_up = 0.5 if spot > ma50 else -0.5
    cyc_fresh = 0.0
    if dc_day is not None and band:
        through = dc_day / max(band[1], 1)
        cyc_fresh = 0.5 - through            # early cycle => +, late => -
        cyc_fresh = float(np.clip(cyc_fresh, -0.6, 0.6))
    d21 = _clip1(0.45 * d3 + 0.30 * trend_up + 0.25 * cyc_fresh)
    # position: primary trend minus how stretched it is above the 200-day
    pos = 0.0
    if pv200 is not None:
        pos += 0.5 if pv200 > 0 else -0.4
        if pv200 >= 25:
            pos -= min(0.6, (pv200 - 25) / 40.0)   # stretched => worse entry
    if pv50 is not None and pv50 < 0:
        pos += 0.15                                 # a pullback below the 50d = better entry
    d63 = _clip1(pos)
    return {"d3": round(d3, 2), "d21": round(d21, 2), "d63": round(d63, 2)}


def assess(close: pd.Series, high: pd.Series | None, rec: dict, *,
           buyable: bool | None = None) -> dict | None:
    """Build the structured entry-timing block for one name, or None when the
    cycle ladder isn't computable. Pure / point-in-time; safe to call per build.

    ``buyable`` is the MACD-2D x StochRSI-3D CONFLUENCE verdict (engine/signal_gate.is_buyable)
    for this name. The daily-cycle ladder this gauge reads can flash an OPEN entry
    (buy_now / partial) while the validated confluence cross has NOT fired — so when the caller
    passes ``buyable=False`` an open entry is HARD-GATED down to an honest "await_confluence"
    wait state (the card never claims the window is open before the validated cross). Pass
    ``buyable=None`` (the default) to leave the gauge ungated — backward compatible for callers
    that don't compute the confluence (e.g. markets without the gate wired)."""
    lad = rec.get("ladder") or {}
    cyc = rec.get("cycle") or {}
    if not lad or not lad.get("state"):
        return None
    c = close.dropna()
    if len(c) < 60:
        return None
    spot = float(c.iloc[-1])
    state = lad.get("state")
    entry = lad.get("entry") or {}
    urg = entry.get("urgency")
    tag = entry.get("tag")

    status = _STATUS_BY_URGENCY.get(urg, "watch")
    # refine: HALF SIZE 'now' is a PARTIAL entry, not a full buy zone
    if status == "buy_now" and tag == "HALF SIZE":
        status = "partial"
    # the cycle-top "don't chase" routes to extended/topping by lateness
    if tag == "DON'T CHASE" or state == "TOP WATCH":
        status = "topping" if cyc.get("dc_phase") == "stretched" else "extended"
    # COUNTERTREND BOUNCE (regime-gate demotion of a fired daily buy) also carries
    # urgency 'caution', but there it means "the turn is not confirmed", NOT
    # "stretched" — the name is typically washed out far BELOW its 200dma. Route it
    # to its own honest status so it never prints "Extended — wait for a pullback".
    if state == "COUNTERTREND BOUNCE" and status == "extended":
        status = "bounce_wait"
    if state == "DECLINE":
        status = "blocked"
    # CONFLUENCE GATE — the daily-cycle ladder above can read an OPEN entry while the validated
    # MACD-2D x StochRSI-3D confluence (engine/signal_gate) has NOT fired. When the caller marks
    # the name not-confluence-buyable, downgrade an open entry (buy_now / partial) to an honest
    # "awaiting confluence cross" wait state; the buy-zone prices still render (it stays a watch
    # zone), but the headline / act-ring no longer claim the window is open before the cross.
    confluence_gated = bool(buyable is False and status in ("buy_now", "partial"))
    if confluence_gated:
        status = "await_confluence"

    ma10, ma20, ma50, ma200 = (_ma(c, 10), _ma(c, 20), _ma(c, 50), _ma(c, 200))
    atrp = _atr_pct(c, high)
    atr = spot * (atrp / 100.0) if atrp else spot * 0.02
    dcl = cyc.get("cand_price") or cyc.get("dcl_price")
    eq_score = lad.get("eq_score")
    band = tuple(cyc.get("dc_band") or (36, 42))
    dc_day = cyc.get("dc_day")

    # ── buy zone (real prices) + don't-chase line + invalidation stop ──────────
    zone_lo = zone_hi = chase_above = None
    if status in ("buy_now", "partial", "buy_soon", "await_confluence"):
        # near a fresh low: accumulate from spot down toward the cycle low; the chase
        # line sits ~half an ATR above spot (paying up past it is chasing the bar).
        zone_hi = _round_px(spot)
        zone_lo = _round_px(max(dcl, spot - 1.5 * atr)) if dcl else _round_px(spot - 1.5 * atr)
        chase_above = _round_px(spot + 0.6 * atr)
    elif status in ("extended", "topping", "wait_pullback", "watch", "hold", "bounce_wait"):
        # a pullback is the constructive entry — target the DAILY-CYCLE supports below
        # spot: the 10-day then 20-day MA. The 50-day is the trend stop, NOT a
        # daily-dip entry, so it is excluded (a vertically-extended name's 50-day can
        # sit -25% away — that's a crash target, not a pullback). The zone depth is
        # capped at ~max(10%, 3·ATR) so an extended leader reads a realistic dip.
        atr_frac = atr / spot if spot else 0.02
        near = [x for x in (ma10, ma20) if x is not None and x < spot * 0.999]
        if near:
            zone_hi = max(near)
            zone_lo = min(near)
        else:
            # price already under both short MAs (or they're above spot): ATR band
            zone_hi = spot - 1.0 * atr
            zone_lo = spot - 2.0 * atr
        deepest = spot * (1 - max(0.10, 3.0 * atr_frac))   # cap the pullback depth
        zone_lo = max(zone_lo, deepest)
        zone_hi, zone_lo = _round_px(zone_hi), _round_px(min(zone_lo, zone_hi))
        chase_above = _round_px(spot)            # don't add at/above here
    stop = _round_px(dcl) if dcl else _round_px((ma50 or spot) * 0.97)

    # zone distance from spot (negative = below spot = a pullback)
    zone_from_spot = None
    if zone_hi is not None and spot:
        mid = (zone_hi + (zone_lo if zone_lo is not None else zone_hi)) / 2.0
        zone_from_spot = round(100 * (mid / spot - 1.0), 1)

    # ── timing window: days to the next cycle-low band (for wait states) ───────
    opens_lo = opens_hi = None
    if status in ("buy_now", "partial"):
        opens_lo = opens_hi = 0
    elif dc_day is not None:
        opens_lo = max(band[0] - dc_day, 0)
        opens_hi = max(band[1] - dc_day, opens_lo + 1)
        btc = (rec.get("mtf") or {}).get("D", {}).get("macd_days_to_cross")
        if btc and status in ("buy_soon", "watch"):
            opens_lo = min(opens_lo or btc, btc)
            opens_hi = min(opens_hi or btc + 3, btc + 3)

    horizon = _horizon_read(rec, eq_score, spot, ma50, ma200, dc_day, band)

    # cycle position (how far through the daily cycle)
    pct_through = None
    if dc_day is not None and band:
        pct_through = int(round(100 * min(dc_day / max(band[1], 1), 1.3)))

    en, zh = _HEADLINE.get(status, _HEADLINE["watch"])
    # a confluence-gated name is "forming, don't act yet" — never the act-now ring, regardless
    # of the (still-fresh) daily-cycle urgency that drove it.
    act = 1 if confluence_gated else _ACT_LEVEL.get(urg, 1)
    out = {
        "status": status,
        "urgency": urg,
        "act_level": act,
        "confluence_gated": confluence_gated,
        "headline": en, "headline_zh": zh,
        "action": entry.get("text"), "action_zh": entry.get("text_zh"),
        "entry_z": eq_score,                       # signed drawdown-calibrated quality
        "entry_grade": lad.get("eq_grade"),
        "confidence": lad.get("bottom_confidence"),   # 0-100 durability (buy states)
        "horizon": horizon,
        "buy_zone": ({"low": zone_lo, "high": zone_hi, "pct_from_spot": zone_from_spot}
                     if zone_hi is not None else None),
        "chase_above": chase_above,
        "stop": stop,
        "spot": _round_px(spot),
        "atr_pct": atrp,
        "timing": {"opens_in_days_lo": opens_lo, "opens_in_days_hi": opens_hi,
                   "next_trigger": entry.get("text")},
        "cycle_pos": {"dc_day": dc_day, "dc_band": list(band),
                      "pct_through": pct_through, "phase": cyc.get("dc_phase")},
    }
    return out
