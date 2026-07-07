"""engine/dannytrades_chip.py — a display-only per-stock CONTRARIAN read derived from
the reconstructed DannyTrades stack (engine/dannytrades.py), wired onto the US stock
detail page.

Evidence status after DT-W1a (2026-07-06, research/dannytrades/DT_W1_RESULTS.md and
research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7):

  1. EXTENSION band (composite-score percentile) — retained as a WEAK TILT display.
     Original evidence: forward-63d return fell monotonically across score deciles
     (Spearman −0.88) on a 64-year, 114-name SURVIVOR panel with no time control.
     The 2021+ survivorship-honest PIT replication, time-controlled (month-block,
     ~60 effective months, single bull regime), found NO significant effect.
  2. WHALE line — DROPPED as a directional claim per the frozen DT-W1 consequence
     rule (H1∧H2∧H3 all FAILED time-controlled: the raw fade/bounce lifts were
     ~85-90% calendar-month base rate). Accumulation values remain as descriptive
     data only; no fade/bounce claim may be derived from them. Restoration path:
     a new prereg in which the 64-year panel survives month-block time control
     (adjudication DT-R13).

NEVER scored, never a price target — a contextual caution chip with its measured
status printed in the caveat. Pure function of one stock's OHLCV.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import dannytrades as dt

WHALE_WIN = 63          # ~3-month accumulation window (daily)
WHALE_CHG = 63          # 3-month change = Danny's "whales entering/leaving"
SCORE_PCT_WIN = 504     # ~2y self-history for the extension percentile

_CAVEAT = ("Contrarian read — the INVERSE of the indicator's usual framing; display-only, "
           "extension band only. Measured on a 64y survivor panel (decile Spearman −0.88, "
           "no time control); the 2021+ survivorship-honest, time-controlled replication "
           "(DT-W1a, ~60 effective months) found NO significant effect, and whale-based "
           "fade/bounce claims were dropped. A weak tilt at best, never a trade.")
_CAVEAT_ZH = ("逆向解读 — 与该指标常规用法相反；仅供展示，仅保留位置分位。原始证据来自64年"
              "幸存股样本（分位 Spearman −0.88，未控制时间因素）；2021年后无幸存偏差、"
              "控制月度基准的复检（DT-W1a，有效样本约60个月）未发现显著效应，"
              "“鲸鱼”方向性判断已移除。至多是微弱倾斜，绝非交易信号。")


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

    # DT-W1a consequence (frozen rule, adjudication §7): the extension band is the ONLY
    # state driver; whale motion carries NO directional claim (descriptive data only).
    if band == "extended":
        state, en, zh = "fade", "Extended — fade risk", "高位 — 谨防回吐"
    elif band == "washed":
        state, en, zh = "bounce", "Washed-out — contrarian setup", "超卖 — 逆向机会"
    else:
        state, en, zh = "neutral", "Neutral", "中性"

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
    detail_en = {
        "fade": "High DannyTrades composite percentile — on the long survivor panel this is "
                "where forward returns faded (unreplicated time-controlled 2021+). A caution "
                "tilt only; don't chase.",
        "bounce": "Low composite percentile — the washed-out side of the long survivor panel "
                  "(unreplicated time-controlled 2021+). A weak contrarian tilt, not a trigger.",
        "neutral": "Mid-range composite percentile — no contrarian extension or washout tilt here.",
    }[state]
    detail_zh = {
        "fade": "DannyTrades 综合分位偏高 — 在长期幸存股样本中此处未来回报曾转弱"
                "（2021年后控制时间因素未复现）。仅为谨慎倾斜，勿追高。",
        "bounce": "综合分位偏低 — 长期幸存股样本中的超卖一侧（2021年后控制时间因素未复现）。"
                  "微弱逆向倾斜，并非触发信号。",
        "neutral": "综合分位处于中段 — 无逆向高位或超卖的倾斜。",
    }[state]

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
