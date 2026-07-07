"""engine/basket_tape.py — volatility black hole · whale accumulation · volume · net flow,
read off a consolidated basket CANDLE.

The single-name DannyTrades reconstruction (engine.dannytrades) already implements every
primitive the user asked for — they just need a candle WITH VOLUME, which engine.basket_index
now supplies (open/high/low/close + traded dollar-volume) for the full membership. We feed it
the basket candle so a THEME gets the same reads a stock does:

  • Volatility black hole — dannytrades.volatility_hole (sticky Bollinger-squeeze box) + a
    realised-volatility percentile, resolved into a regime: IN_HOLE (coiling, no edge yet),
    COILED_UP/COILED_DOWN (pressed against an edge) or EXPANSION_UP/DOWN (the box just broke).
  • Whale accumulation — dannytrades.whale_accumulation (Chaikin-money-flow percentile 0–100):
    describes the accumulation-level band of the basket. DISPLAY-ONLY, descriptive — DT-W1a
    (2026-07-06) found all DannyTrades directional reads FAILED time-controlled replication
    (~60 effective months, month-block control); whale-based directional claims (fade/bounce)
    were dropped. Labels and fields are descriptive-only (accumulation level), not forecasts.
  • Volume — basket TRADED DOLLAR-VOLUME and its surge z-score (raw share volume is meaningless
    across different-priced members; dollars are the right unit).
  • Net inflow/outflow — Chaikin Money Flow on the candle (dollar-weighted close-in-range), i.e.
    the net of accumulation vs distribution; + OBV trend and 5/20-day net money-flow.

The vol-hole leg is the ONE piece wired into the score (an expansion that RESOLVES up/down is
the only directional content; a squeeze itself is "coiled, wait"). Whale / volume / net-flow
are DISPLAY-ONLY context (`directional: False`) — useful colour, but cross-sectional flow has
~0 validated forward edge (house finding), so they describe state, they don't forecast.

DT-W1a evidence status (adjudication 2026-07-06,
research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7):
  - All DannyTrades directional reads FAILED time-controlled replication.
  - danny.buy / danny.sell / danny.buy_strong: descriptive composite-checklist state flags —
    NOT directional buy/sell signals; present for structural completeness only.
  - out["danny_caveat"]: imported from engine.dannytrades_chip._CAVEAT for downstream display.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import dannytrades as dt
from engine.dannytrades_chip import _CAVEAT as _DT_CAVEAT_EN, _CAVEAT_ZH as _DT_CAVEAT_ZH

log = logging.getLogger(__name__)


def _pctile(s: pd.Series, win: int = 252) -> float | None:
    s = s.dropna()
    if len(s) < 30:
        return None
    seg = s.iloc[-win:]
    return float((seg <= seg.iloc[-1]).mean())


def _realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    return close.pct_change().rolling(n, min_periods=max(5, n // 2)).std() * np.sqrt(252)


def _volhole(close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
    """Bollinger-squeeze box + realised-vol percentile → one regime + a bounded score leg."""
    hole = dt.volatility_hole(close, high, low)
    last = hole.iloc[-1]
    bw = dt.bb_bandwidth(close)
    bw_pct = _pctile(bw, dt.CFG["squeeze_lookback"])
    rv = _realized_vol(close)
    rv_pct = _pctile(rv)
    in_hole = bool(last["in_hole"])
    breakout = bool(last["breakout_up"])
    breakdown = bool(last["breakdown"])
    pos = float(last["pos_in_box"]) if pd.notna(last["pos_in_box"]) else None
    compressed = (bw_pct is not None and bw_pct <= dt.CFG["squeeze_pctile"]) or \
                 (rv_pct is not None and rv_pct <= 0.25)

    # recent expansion = a breakout/breakdown in the last few sessions
    recent = hole.iloc[-5:]
    recent_up = bool(recent["breakout_up"].any())
    recent_dn = bool(recent["breakdown"].any())

    if breakout or (recent_up and not in_hole):
        state, en, zh, score = "EXPANSION_UP", "Breaking out of the hole", "突破波动洞", 0.8
    elif breakdown or (recent_dn and not in_hole):
        state, en, zh, score = "EXPANSION_DOWN", "Breaking down out of the hole", "向下跌破波动洞", -0.8
    elif in_hole and compressed:
        # coiled — lean to the side it's pressed against, but small (no resolution yet)
        if pos is not None and pos >= 0.66:
            state, en, zh, score = "COILED_UP", "Coiled, pressing the top", "蓄势，逼近上沿", 0.25
        elif pos is not None and pos <= 0.34:
            state, en, zh, score = "COILED_DOWN", "Coiled, pressing the bottom", "蓄势，逼近下沿", -0.25
        else:
            state, en, zh, score = "IN_HOLE", "In the hole — compressed, coiling", "处于波动洞内 — 压缩蓄势", 0.0
    elif in_hole:
        state, en, zh, score = "IN_HOLE", "Inside the range — no compression", "区间内 — 无明显压缩", 0.0
    else:
        state, en, zh, score = "EXPANDED", "Trending outside the box", "已脱离压缩区运行", 0.1 if (pos or 0.5) > 0.5 else -0.1

    return {
        "state": state, "label_en": en, "label_zh": zh,
        "compressed": bool(compressed),
        "bandwidth_pctile": round(bw_pct, 3) if bw_pct is not None else None,
        "realized_vol_pctile": round(rv_pct, 3) if rv_pct is not None else None,
        "pos_in_box": round(pos, 3) if pos is not None else None,
        "to_upper_pct": round(float(last["to_upper_pct"]), 2) if pd.notna(last["to_upper_pct"]) else None,
        "to_lower_pct": round(float(last["to_lower_pct"]), 2) if pd.notna(last["to_lower_pct"]) else None,
        "breakout_up": breakout, "breakdown": breakdown,
        "score": float(score),     # the bounded leg fed to theme_scoring (−1..1)
        "directional": True,       # the only directional piece — an expansion that resolves
    }


def _whale(close, high, low, dvol) -> dict:
    # DT-W1a (2026-07-06): directional reads failed time-controlled replication.
    # Labels are accumulation-level descriptions only — no directional/promise framing.
    w = dt.whale_accumulation(high, low, close, dvol)
    cur = float(w.iloc[-1]) if pd.notna(w.iloc[-1]) else None
    d5 = float(w.iloc[-1] - w.iloc[-6]) if len(w.dropna()) > 6 and pd.notna(w.iloc[-6]) else None
    if cur is None:
        band, en, zh = "unknown", "—", "—"
    elif cur >= dt.CFG["whale_soar"]:
        band, en, zh = "soaring", "Accumulation high", "吸筹水平高"
    elif cur >= dt.CFG["whale_momentum"]:
        band, en, zh = "accumulating", "Accumulation elevated", "吸筹水平偏高"
    elif cur >= 35:
        band, en, zh = "building", "Accumulation moderate", "吸筹水平中等"
    else:
        band, en, zh = "distributing", "Accumulation low", "吸筹水平偏低"
    return {"accumulation": round(cur, 1) if cur is not None else None,
            "trend_5d": round(d5, 1) if d5 is not None else None,
            "band": band, "label_en": en, "label_zh": zh,
            "rising": bool(d5 is not None and d5 > 0), "directional": False}


def _flow(close, high, low, dvol) -> dict:
    """Net inflow/outflow = Chaikin Money Flow (dollar-weighted close-in-range) + OBV trend +
    5/20-day net money-flow + a dollar-volume surge z-score. Display-only."""
    cmf = dt.cmf(high, low, close, dvol)
    cur = float(cmf.iloc[-1]) if pd.notna(cmf.iloc[-1]) else None
    mfv = dt.money_flow_volume(high, low, close, dvol)
    nf5 = float(mfv.iloc[-5:].sum())
    nf20 = float(mfv.iloc[-20:].sum())
    obv = dt.obv(close, dvol)
    obv_slope = float(obv.iloc[-1] - obv.iloc[-21]) if len(obv) > 21 else None
    dv = dvol.dropna()
    dv_last = float(dv.iloc[-1]) if not dv.empty else None
    # SURGE = recent 5-day dollar volume vs its trailing-median baseline (a ratio, not a z —
    # secular volume growth would inflate a z permanently and read as a perpetual "surge").
    dv_surge = None
    if len(dv) > 40:
        recent = float(dv.iloc[-5:].mean())
        base = float(dv.iloc[-63:].median()) if len(dv) > 63 else float(dv.median())
        dv_surge = round(recent / base, 2) if base else None
    if cur is None:
        en, zh = "—", "—"
    elif cur > 0.05:
        en, zh = "Net inflow (accumulation)", "净流入（吸筹）"
    elif cur < -0.05:
        en, zh = "Net outflow (distribution)", "净流出（派发）"
    else:
        en, zh = "Balanced flow", "资金流均衡"
    return {"cmf": round(cur, 3) if cur is not None else None,
            "net_flow_5d": nf5, "net_flow_20d": nf20,
            "obv_rising": bool(obv_slope is not None and obv_slope > 0),
            "dollar_vol": dv_last, "dollar_vol_surge": dv_surge,
            "inflow": bool(cur is not None and cur > 0),
            "label_en": en, "label_zh": zh, "directional": False}


def basket_tape(candle: pd.DataFrame | None, coverage: dict | None = None) -> dict:
    """Vol-hole + whale + volume + net-flow for one basket candle (open/high/low/close/dollar_vol).
    {} on short history or failure (additive caller)."""
    if candle is None or candle.empty or "close" not in candle:
        return {}
    try:
        close = candle["close"].dropna().astype(float)
        if len(close) < 60:
            return {}
        idx = close.index
        high = candle["high"].reindex(idx).astype(float)
        low = candle["low"].reindex(idx).astype(float)
        dvol = candle["dollar_vol"].reindex(idx).astype(float) if "dollar_vol" in candle else None
        has_vol = dvol is not None and dvol.notna().sum() > 30

        out = {"volhole": _volhole(close, high, low), "as_of": str(idx.max().date())}
        if has_vol:
            sig = dt.signals(close, high, low, dvol.fillna(0.0))
            last = sig.iloc[-1]
            out["whale"] = _whale(close, high, low, dvol)
            out["flow"] = _flow(close, high, low, dvol)
            # DT-W1a: buy/sell/buy_strong are composite-checklist STATE flags, not
            # directional signals — directional reads failed time-controlled replication.
            out["danny"] = {
                "score": round(float(last["score"]), 1) if pd.notna(last["score"]) else None,
                "buy": bool(last["danny_buy"]), "buy_strong": bool(last["danny_buy_strong"]),
                "sell": bool(last["danny_sell"]), "ribbon": int(last["ribbon"]),
                "above_poc": bool(last["above_poc"]), "directional": False,
            }
            out["danny_caveat"] = {"en": _DT_CAVEAT_EN, "zh": _DT_CAVEAT_ZH}
        else:
            out["whale"] = out["flow"] = None
        if coverage:
            out["coverage"] = {"n_live": coverage.get("n_live"),
                               "n_with_volume": coverage.get("n_live_with_volume"),
                               "coverage_pct": coverage.get("coverage_pct")}
        return out
    except Exception as e:  # noqa: BLE001 — additive overlay
        log.warning("basket_tape failed: %s", e)
        return {}
