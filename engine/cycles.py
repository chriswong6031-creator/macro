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
    return {
        "macd_pos": bool(hist.iloc[-1] > 0),
        "macd_cross_up": cross_up, "macd_cross_dn": cross_dn,
        "macd_approaching_up": approaching_up, "macd_approaching_dn": approaching_dn,
        "macd_bars_to_cross": round(bars_to_cross, 1) if bars_to_cross else None,
        "rsi14": round(float(r14.iloc[-1]), 0) if pd.notna(r14.iloc[-1]) else None,
        "rsi5": round(float(r5.iloc[-1]), 0) if pd.notna(r5.iloc[-1]) else None,
        "stoch": round(float(srsi.iloc[-1]), 0) if pd.notna(srsi.iloc[-1]) else None,
    }


def mtf_snapshot(close: pd.Series) -> dict:
    """Daily / 3-day / weekly indicator states."""
    daily = close.dropna()
    return {
        "D": _tf_state(daily),
        "3D": _tf_state(daily.resample("3B").last().dropna()) if len(daily) > 150 else {},
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


def cycle_state(close: pd.Series, high: pd.Series | None = None) -> dict:
    """Daily + investor cycle position for one instrument."""
    c = close.dropna()
    if len(c) < 260:
        return {}
    troughs = find_troughs(c)
    if not troughs:
        return {}
    last_dcl = troughs[-1]
    dc_day = int(len(c.loc[last_dcl:]) - 1)
    dcl_price = float(c.loc[last_dcl])

    # candidate for the NEXT cycle low: the lowest bar of the recent decline.
    # Only meaningful once the cycle is old enough that a new low is due.
    cand_day = cand_price = cand_swing = cand_age = None
    if dc_day >= DC_BAND[0] - 10:
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

    if dc_day < DC_EARLY:
        dc_phase = "new"
    elif dc_day < DC_BAND[0] - 8:
        dc_phase = "mid"
    elif dc_day < DC_BAND[0]:
        dc_phase = "approaching_band"
    elif dc_day <= DC_BAND[1]:
        dc_phase = "in_band"
    else:
        dc_phase = "stretched"

    ic_phase = None
    if ic_week is not None:
        ic_phase = ("early" if ic_week <= 6 else "mid" if ic_week <= 13 else
                    "late" if ic_week <= IC_BAND_W[1] else "overdue")

    return {
        "dc_day": dc_day, "dc_band": DC_BAND, "dc_phase": dc_phase,
        "last_dcl": str(last_dcl.date()), "dcl_price": round(dcl_price, 2),
        "cand_dcl": cand_day, "cand_price": round(cand_price, 2) if cand_price else None,
        "cand_swing": cand_swing, "cand_age": cand_age,
        "translation": translation, "failed_cycle": failed,
        "swing_low": swing_low, "above_ma10": above_ma10, "ma10_rising": ma10_rising,
        "ic_week": ic_week, "ic_phase": ic_phase, "ic_failed": ic_failed,
        "n_troughs": len(troughs),
    }


# ----------------------------------------------------------- signal ladder ----

LADDER = ["DECLINE", "BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY",
          "RALLY ON", "TOP WATCH", "ROLLING OVER"]

LADDER_SCORE = {"DECLINE": -80, "ROLLING OVER": -40, "TOP WATCH": -10,
                "BOTTOM WATCH": 10, "TURN SIGNALED": 45, "FRESH BUY": 80,
                "RALLY ON": 55}


def ladder_state(cyc: dict, mtf: dict) -> dict:
    """Combine cycle position + multi-timeframe indicators into one state,
    with a plain next-step line. Weekly timeframe gates the daily signal."""
    if not cyc or not mtf.get("D"):
        return {}
    d, w = mtf["D"], mtf.get("W", {})
    weekly_ok = bool(w.get("macd_pos") or w.get("macd_approaching_up")) and not cyc["ic_failed"]

    state, why, nxt = None, "", ""
    late = cyc["dc_phase"] in ("approaching_band", "in_band", "stretched")
    # a late-cycle decline hunts the NEXT low via the candidate trough
    cand_confirmed = bool(late and cyc.get("cand_swing") and cyc["above_ma10"])

    if cyc["failed_cycle"] and not cyc["above_ma10"]:
        state = "DECLINE"
        why = ("Failed cycle — price broke below the low that started this cycle, "
               "which historically means the larger trend is rolling over (~80% of cases).")
        nxt = "Stand aside until a new daily cycle low forms and confirms."
    elif cand_confirmed and (d.get("macd_cross_up") or d.get("macd_pos")
                             or d.get("macd_approaching_up")):
        state = "FRESH BUY" if weekly_ok else "TURN SIGNALED"
        why = (f"A new cycle low likely formed {cyc['cand_age']} day(s) ago "
               f"({cyc['cand_dcl']} @ {cyc['cand_price']}): swing low in, price back "
               "above the 10-day average"
               + (" — and the weekly timeframe agrees." if weekly_ok else
                  " — but the weekly timeframe hasn't turned yet, so conviction is partial."))
        nxt = (f"The cleanest setup cycle logic offers — entry with a defined exit: "
               f"invalidation = a close below {cyc['cand_price']}.") if weekly_ok else \
              "Either wait for the weekly to turn, or size half until it does."
    elif late and cyc.get("cand_swing") and not cyc["above_ma10"]:
        state = "TURN SIGNALED"
        why = (f"Buyers rejected the {cyc['cand_dcl']} low (swing low printed) but price "
               "hasn't reclaimed its 10-day average — first box ticked, not all.")
        nxt = "Confirmation = a close above the 10-day average with the average turning up."
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            nxt += f" Daily momentum is ~{d['macd_bars_to_cross']:.0f} bars from its bullish cross."
    elif late and not cyc["above_ma10"]:
        state = "BOTTOM WATCH"
        why = (f"Day {cyc['dc_day']} of a typical {DC_BAND[0]}-{DC_BAND[1]}-day cycle — "
               "inside the window where lows usually form"
               + (", and short-term momentum is washed out" if (d.get("rsi5") or 50) < 30 else "")
               + ". No confirmed turn yet.")
        nxt = ("Wait for the turn: a move above the low candle's high, then a close back "
               "above the 10-day average.")
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            nxt += f" Daily momentum is ~{d['macd_bars_to_cross']:.0f} bars from a bullish cross."
    elif d.get("macd_cross_dn") and not cyc["above_ma10"] and cyc["dc_day"] > DC_EARLY:
        state = "ROLLING OVER"
        why = "Daily momentum just crossed down and price lost its 10-day average mid-cycle."
        nxt = ("Trim or tighten stops; next likely support is the daily-cycle timing band "
               f"(~day {DC_BAND[0]}-{DC_BAND[1]}, now day {cyc['dc_day']}).")
    elif cyc["swing_low"] and cyc["dc_day"] <= DC_EARLY and cyc["above_ma10"] \
            and (d.get("macd_cross_up") or d.get("macd_pos")):
        state = "FRESH BUY" if weekly_ok else "TURN SIGNALED"
        why = (f"New daily cycle, day {cyc['dc_day']}: swing low in, price back above the "
               "10-day average, daily momentum positive"
               + (" — and the weekly timeframe agrees." if weekly_ok else
                  " — but the weekly timeframe hasn't turned yet, so conviction is partial."))
        nxt = ("The highest-odds window by cycle logic; invalidation = a close below "
               f"the cycle low ({cyc['dcl_price']}).") if weekly_ok else \
              "Either wait for the weekly to turn, or size half until it does."
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
            nxt = ("Not a short signal — just don't add here; pullbacks to the 10-day "
                   "average are normal.")
        else:
            state = "RALLY ON"
            why = (f"Day {cyc['dc_day']} of the cycle, trend intact above a rising 10-day average"
                   + (", weekly aligned." if weekly_ok else ", weekly still mixed."))
            nxt = ("Hold; first warning would be losing the 10-day average, bigger warning is a "
                   "daily momentum cross down.")
    elif late and cyc["above_ma10"]:
        state = "TOP WATCH"
        why = (f"Late in the daily cycle (day {cyc['dc_day']} of ~{DC_BAND[0]}-{DC_BAND[1]}) — "
               "odds favor a dip into the next cycle low from here even with the trend intact.")
        nxt = "Let the next daily cycle low form before adding; watch for the swing-low setup."
    else:
        state = "RALLY ON" if cyc["above_ma10"] else "BOTTOM WATCH"
        why = "Mixed structure."
        nxt = "Watch the 10-day average and cycle-day count."

    score = LADDER_SCORE[state]
    if cyc.get("translation") == "left":
        score -= 10
        why += " Last cycle was left-translated (topped early) — a bearish structural tell."
    if state in ("FRESH BUY", "RALLY ON") and cyc.get("translation") == "right":
        score += 5

    return {"state": state, "score": int(np.clip(score, -100, 100)),
            "why": why, "next": nxt, "weekly_ok": weekly_ok}


def analyze(close: pd.Series, high: pd.Series | None = None) -> dict:
    cyc = cycle_state(close, high)
    mtf = mtf_snapshot(close)
    lad = ladder_state(cyc, mtf)
    return {"cycle": cyc, "mtf": mtf, "ladder": lad}


# ------------------------------------------------------------- calibration ----

def calibrate_ladder(price_panel: dict[str, pd.Series], fwd: int = 21,
                     step: int = 5) -> dict:
    """Historical forward returns by ladder state. price_panel: name -> close.
    Heavy-ish (re-evaluates state along history) — run by the validation
    pipeline, cached to data/regime/ladder_calibration.json."""
    buckets: dict[str, list[float]] = {s: [] for s in LADDER}
    for name, close in price_panel.items():
        c = close.dropna()
        if len(c) < 600:
            continue
        fwd_ret = c.pct_change(fwd).shift(-fwd)
        # walk weekly through history; a trailing 600-day window is all the
        # cycle/indicator math needs and keeps the walk-forward tractable
        for i in range(300, len(c) - fwd, step):
            sub = c.iloc[max(0, i - 600):i + 1]
            try:
                st = ladder_state(cycle_state(sub), {"D": _tf_state(sub),
                                                     "W": _tf_state(sub.resample("W-FRI").last().dropna())})
            except Exception:  # noqa: BLE001
                continue
            if st.get("state"):
                v = fwd_ret.iloc[i]
                if pd.notna(v):
                    buckets[st["state"]].append(float(v))
    out = {}
    for s, vals in buckets.items():
        if len(vals) >= 40:
            a = np.array(vals)
            out[s] = {"n": len(a), "hit_pct": round(100 * (a > 0).mean(), 1),
                      "avg_fwd_pct": round(100 * a.mean(), 2)}
    return out
