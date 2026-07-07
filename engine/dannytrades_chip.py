"""engine/dannytrades_chip.py — a display-only per-stock DESCRIPTIVE positioning
readout derived from the reconstructed DannyTrades stack (engine/dannytrades.py),
wired onto the US stock detail page.

Evidence status after DT-W1a + DT-W2 (2026-07-06; research/dannytrades/
DT_W1_RESULTS.md, DT_W2_64Y_RESULTS.md, and
research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7-§8):

  ALL directional reads are RETIRED. The 2021+ survivorship-honest, time-controlled
  replication (DT-W1a) failed all four contrarian reads; the 64-year month-block
  settlement (DT-W2) failed three of four, and the one pooled survivor
  (whale-surge fade, p=0.004) is a PRE-2010 phenomenon — null 2011-2026
  (−0.5pp, CI spans zero, p=0.33) on top of survivor-flatter — so restoration
  was DENIED (adjudication §8, DT-R15). The chip now reports only:
    - extension percentile of the composite vs its own 2y history (descriptive band)
    - accumulation level/motion (descriptive values, no direction)
  state is always "neutral" (enum kept for dt_contra_state.json schema stability).

NEVER scored, never a price target, no tilt claims. Pure function of one stock's OHLCV.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import dannytrades as dt

WHALE_WIN = 63          # ~3-month accumulation window (daily)
WHALE_CHG = 63          # 3-month change = Danny's "whales entering/leaving"
SCORE_PCT_WIN = 504     # ~2y self-history for the extension percentile

_CAVEAT = ("Descriptive positioning readout only — no directional read. Time-controlled "
           "replication retired all contrarian claims (2026-07-06): the 2021+ "
           "survivorship-honest panel was all-null (DT-W1a), and on the 64y panel the one "
           "pooled survivor (accumulation-surge fade) is null in the modern era "
           "(2011-2026 CI spans zero) and survivor-flattered (DT-W2). Values describe "
           "where the name sits; they do not predict.")
_CAVEAT_ZH = ("仅为描述性位置读数 — 无方向性判断。控制时间因素的复检已于2026-07-06退役全部"
              "逆向解读：2021年后无幸存偏差样本全部无效应（DT-W1a）；64年样本中唯一合并显著项"
              "（吸筹激增后转弱）在2011-2026年代为零效应且受幸存偏差夸大（DT-W2）。"
              "数值仅描述所处位置，不构成预测。")


def _band(p: float) -> str:
    return "extended" if p >= 0.80 else "elevated" if p >= 0.60 \
        else "washed" if p <= 0.20 else "neutral"


def assess(close: pd.Series, high: pd.Series | None, low: pd.Series | None,
           volume: pd.Series | None) -> dict | None:
    """Per-stock contrarian read. Returns None when OHLCV is too thin / volume absent."""
    if high is None or low is None or volume is None:
        return None
    close = close.astype(float).dropna()
    if len(close) < 260:
        return None
    high = high.astype(float).reindex(close.index)
    low = low.astype(float).reindex(close.index)
    volume = volume.astype(float).reindex(close.index).fillna(0.0)
    if (volume > 0).sum() < 200:                       # need real historical volume
        return None

    sig = dt.signals(close, high, low, volume)
    whale = dt.whale_buy_fraction(high, low, close, volume, WHALE_WIN)
    score = sig["score"]
    score_pct = score.rolling(SCORE_PCT_WIN, min_periods=120).rank(pct=True)

    w = float(whale.iloc[-1]) if pd.notna(whale.iloc[-1]) else None
    wchg = float(whale.iloc[-1] - whale.iloc[-1 - WHALE_CHG]) \
        if len(whale) > WHALE_CHG and pd.notna(whale.iloc[-1]) \
        and pd.notna(whale.iloc[-1 - WHALE_CHG]) else None
    spct = float(score_pct.iloc[-1]) if pd.notna(score_pct.iloc[-1]) else None
    if w is None or spct is None:
        return None

    band = _band(spct)
    rising = (wchg is not None and wchg > 5)
    falling = (wchg is not None and wchg < -5)

    # DT-W2 consequence (frozen rule, adjudication §8): H4 failed on BOTH panels →
    # ALL directional tilt claims retired. The chip is a descriptive positioning
    # readout only; state stays "neutral" (enum stability for dt_contra_state.json).
    state = "neutral"
    en = f"Extension {int(round(spct * 100))}th percentile"
    zh = f"位置分位 {int(round(spct * 100))}"

    whale_state = ("entering" if rising else "leaving" if falling else "quiet")
    whale_lbl = {"entering": ("Accumulation rising", "吸筹上升"),
                 "leaving": ("Accumulation falling", "吸筹回落"),
                 "quiet": ("Accumulation quiet", "吸筹平静")}[whale_state]

    chips = [
        {"key": "ext", "cls": band,
         "label": {"en": f"Extension {int(round(spct * 100))}th pctile",
                   "zh": f"位置 {int(round(spct * 100))} 分位"}},
        {"key": "whale", "cls": whale_state,
         "label": {"en": f"{whale_lbl[0]} · {int(round(w))}%",
                   "zh": f"{whale_lbl[1]} · {int(round(w))}%"}},
    ]
    detail_en = ("Descriptive positioning readout: where the DannyTrades composite sits in its "
                 "own 2-year history, plus the accumulation level. No directional implication — "
                 "both contrarian reads were retired after time-controlled replication failed "
                 "(DT-W1a/DT-W2, 2026-07-06).")
    detail_zh = ("描述性位置读数：DannyTrades 综合分在自身两年历史中的分位，以及吸筹水平。"
                 "无方向性含义 — 两项逆向解读在控制时间因素的复检失败后已于 2026-07-06 退役"
                 "（DT-W1a/DT-W2）。")

    return {
        "state": state,
        "headline": {"en": en, "zh": zh},
        "score_pct": round(spct, 3), "band": band,
        "whale": round(w, 1), "whale_chg": (round(wchg, 1) if wchg is not None else None),
        "whale_state": whale_state,
        "chips": chips,
        "detail": {"en": detail_en, "zh": detail_zh},
        "caveat": {"en": _CAVEAT, "zh": _CAVEAT_ZH},
    }
