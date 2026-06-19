"""Per-theme ATR extension — the "too hot / chase-risk" texture (DISPLAY-ONLY).

The stable_market_board's signature read is ATR-extension: how many average true ranges a
name sits above its 50-day MA. It is the cleanest "this has run too far, too fast" flag.
This ports the idea to OUR thematic baskets as a per-theme texture chip to sit beside the
Theme Rotation Desk: for each basket, the EQUAL-WEIGHT level's distance above its 50d MA in
ATR units, plus the share of constituents that are stretched / parabolic.

METHODOLOGY NOTE — close-based ATR. Our basket level and the free S&P-1500 close cache are
CLOSE-ONLY (no intraday high/low), so we use a close-based ATR proxy: a Wilder EMA
(alpha=1/14) of the absolute daily change. atr_ext = (price - SMA50) / ATR_close. This runs
slightly hotter than a true-range ATR (no intraday range in the denominator), so the bands
below are calibrated for close-based units and the metric is labelled as such. Region-aware
via engine.group_flow._setup so CN/HK/CA work once that is regionalised.

HONEST BY CONSTRUCTION: a risk/extension texture, never a buy/sell, never scored.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import group_flow
from lib import config  # noqa: F401  (kept for parity / future config knobs)

log = logging.getLogger(__name__)

MA_WINDOW = 50
ATR_WINDOW = 14
# Per-member close-based ATR bands (units = ATRs above the 50d MA). The HEADLINE per-theme
# number is the MEDIAN MEMBER extension — directly comparable to the stable board's per-name
# atr_ext (a smoothed equal-weight basket level has tiny daily vol, so its own ATR-ext is
# inflated and is kept only as a secondary reference, not the band/sort driver).
STRETCHED = 3.0     # member is getting extended
PARABOLIC = 5.0     # member is parabolic / chase-risk
# theme bands off the MEDIAN MEMBER extension
BAND_PARABOLIC = 5.0
BAND_STRETCHED = 3.0
BAND_EXTENDED = 1.5
BAND_WASHED = -2.0


def _r(x, n: int = 2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def _atr_ext(series: pd.Series, ma_window: int = MA_WINDOW, atr_window: int = ATR_WINDOW) -> float | None:
    """Latest (price - SMA{ma_window}) / close-based-ATR{atr_window}, in ATR units."""
    s = series.dropna()
    if len(s) < ma_window + atr_window:
        return None
    atr = s.diff().abs().ewm(alpha=1.0 / atr_window, adjust=False, min_periods=atr_window).mean()
    ma = s.rolling(ma_window, min_periods=ma_window // 2).mean()
    ext = (s - ma) / atr.replace(0, np.nan)
    v = ext.iloc[-1]
    return float(v) if pd.notna(v) else None


def _mt(m: dict):
    return m.get("ticker") or m.get("symbol")


def _band(ext: float | None) -> tuple[str, str, str]:
    if ext is None:
        return "—", "—", "neu"
    if ext >= BAND_PARABOLIC:
        return "parabolic", "抛物线", "neg"
    if ext >= BAND_STRETCHED:
        return "stretched", "延展", "warn"
    if ext >= BAND_EXTENDED:
        return "extended", "偏高", "warn"
    if ext <= BAND_WASHED:
        return "washed out", "超卖", "pos"
    return "normal", "正常", "neu"


def compute_theme_extension(region: str = "us") -> dict | None:
    """Per-basket ATR-extension texture for a region. None on shortfall (additive caller)."""
    s = group_flow._setup(region)
    if s is None:
        return None
    closes, rets, idx, bench = s["closes"], s["rets"], s["idx"], s["bench"]
    if len(idx) < MA_WINDOW + ATR_WINDOW:
        return None

    bdict = s["mem"]["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    rows = []
    for bid, b in items:
        members = b.get("members", [])
        present = [_mt(m) for m in members if _mt(m) in rets.columns]
        present = [t for t in present if t]
        if len(present) < 3:
            continue
        lvl = group_flow._ew_level(rets, members, idx)
        if lvl.dropna().empty:
            continue
        # live members today (dated [added, removed) mask, mirrors group_flow)
        live = []
        last = idx.max()
        for m in members:
            t = _mt(m)
            if t not in present:
                continue
            if pd.Timestamp(m.get("added")) <= last and (
                    not m.get("removed") or pd.Timestamp(m["removed"]) > last):
                live.append(t)
        if len(live) < 3:
            continue

        basket_ext = _atr_ext(lvl)
        member_ext = [e for e in (_atr_ext(closes[t]) for t in live) if e is not None]
        n = len(member_ext)
        if not n:
            continue
        med = float(np.median(member_ext))
        pct_stretched = sum(1 for e in member_ext if e >= STRETCHED) / n
        pct_parabolic = sum(1 for e in member_ext if e >= PARABOLIC) / n
        band_en, band_zh, tone = _band(med)        # headline = median member extension
        rows.append({
            "id": bid, "name": b.get("name", bid),
            "name_zh": b.get("name_zh", b.get("name", bid)),
            "category": b.get("category", "Other"),
            "atr_ext": _r(med),                      # headline (median member, comparable to per-name)
            "basket_ext": _r(basket_ext),            # secondary: the smoothed EW-level extension
            "pct_stretched": _r(pct_stretched, 2), "pct_parabolic": _r(pct_parabolic, 2),
            "n_live": len(live), "band_en": band_en, "band_zh": band_zh, "tone": tone,
        })
    if not rows:
        return None
    rows.sort(key=lambda x: (x["atr_ext"] is None, -(x["atr_ext"] or -1e9)))
    return {
        "as_of": idx.max().strftime("%Y-%m-%d"),
        "region": s.get("region", region),
        "method": "close-based ATR (Wilder EMA of |Δclose|, alpha=1/14); ext = (price - SMA50) / ATR",
        "bands": {"extended": BAND_EXTENDED, "stretched": BAND_STRETCHED,
                  "parabolic": BAND_PARABOLIC, "washed": BAND_WASHED},
        "disclaimer_en": ("Display-only extension texture — how far each theme has run above "
                          "its 50d trend in ATR units. A chase-risk flag, never a buy/sell."),
        "disclaimer_zh": ("仅供展示的延展纹理 — 各主题相对其50日趋势的延展程度（ATR 单位）。"
                          "追高风险提示，非买卖信号。"),
        "themes": rows,
        "hot": [r for r in rows if (r["atr_ext"] or 0) >= BAND_STRETCHED][:8],
    }
