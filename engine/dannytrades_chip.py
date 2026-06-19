"""engine/dannytrades_chip.py — a display-only per-stock CONTRARIAN read derived from
the reconstructed DannyTrades stack (engine/dannytrades.py), wired onto the US stock
detail page.

It surfaces the TWO findings that survived the phase-0 gate (research/DANNYTRADES_PHASE0.md)
— both contrarian, i.e. the INVERSE of how Danny trades them:

  1. EXTENSION — a high composite score flags an *extended* name that tends to
     mean-revert: forward-63d return falls monotonically across all ten score deciles
     (Spearman −0.88). High score → "don't chase".
  2. WHALE FADE — "whales entering" (his rising-accumulation tell) precedes
     UNDER-performance, not out-: monthly IC of the accumulation change is −0.023
     (t ≈ −3.9); "whales leaving" precedes out-performance. So hot+rising whale
     accumulation = distribution/fade risk; bled-out = a bounce setup.

NEVER scored, never a price target — a contextual caution chip with the validated
stats printed in its caveat. Pure function of one stock's OHLCV. Honest limits: the
validation is on a 114-name large-cap SURVIVOR panel; treat as a tilt, not a trade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import dannytrades as dt

WHALE_WIN = 63          # ~3-month accumulation window (daily)
WHALE_CHG = 63          # 3-month change = Danny's "whales entering/leaving"
SCORE_PCT_WIN = 504     # ~2y self-history for the extension percentile

_CAVEAT = ("Contrarian read — the INVERSE of the indicator's usual framing. Validated "
           "(display-only) that a high composite flags lower forward-63d returns "
           "(decile Spearman −0.88) and that rising 'whale accumulation' precedes "
           "under-performance (monthly IC t≈−3.9). Large-cap survivor sample; a tilt, "
           "not a trade.")
_CAVEAT_ZH = ("逆向解读 — 与该指标常规用法相反。经验证（仅供展示）：高综合分预示未来63日"
              "回报更低（分位单调 Spearman −0.88），且“鲸鱼吸筹”上升反而领先跑输"
              "（月度 IC t≈−3.9）。样本为大盘幸存股；是倾斜而非交易信号。")


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
    entering = (wchg is not None and wchg > 5 and w >= 55)      # hot + rising → fade
    leaving = (wchg is not None and wchg < -5)                  # bleeding out → improving

    # contrarian verdict — the extension band (Spearman −0.88, the stronger leg) leads;
    # the whale change is a secondary tilt that can resolve a mid-range band.
    if band == "extended":
        state, en, zh = "fade", "Extended — fade risk", "高位 — 谨防回吐"
    elif band == "washed":
        state, en, zh = "bounce", "Washed-out — contrarian setup", "超卖 — 逆向机会"
    elif entering:
        state, en, zh = "fade", "Whales crowding — fade risk", "鲸鱼拥挤 — 谨防回吐"
    elif leaving:
        state, en, zh = "bounce", "Accumulation bleeding — improving", "吸筹枯竭 — 转好"
    else:
        state, en, zh = "neutral", "Neutral", "中性"

    whale_state = ("entering" if entering else "leaving" if leaving else "quiet")
    whale_lbl = {"entering": ("Whales entering (fade)", "鲸鱼吸筹（宜淡出）"),
                 "leaving": ("Whales leaving (improving)", "鲸鱼撤离（转好）"),
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
        "fade": "High DannyTrades composite / hot-and-rising accumulation — historically "
                "this is where forward returns fade. Don't chase; wait for a reset.",
        "bounce": "Bled-out accumulation with a low composite — the washed-out side where "
                  "forward returns have historically been better. A contrarian setup, not a trigger.",
        "neutral": "Mid-range composite and accumulation — no contrarian extension or washout edge here.",
    }[state]
    detail_zh = {
        "fade": "DannyTrades 综合分偏高 / 吸筹过热且上升 — 历史上正是未来回报转弱之处。勿追高，等待回落。",
        "bounce": "吸筹枯竭且综合分偏低 — 超卖一侧，历史上未来回报更佳。逆向机会，并非触发信号。",
        "neutral": "综合分与吸筹均处中位 — 无逆向高位或超卖的边际。",
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
