"""engine/oracle/washout_counterread.py — the washout counter-read (Rotation Command RC-R11).

On 2026-06-26 — the exact session the Mag-7 complex bottomed — the risk layer printed its
MAXIMUM growth-scare reading (90.8, risk-off band). A defensive score peaking on the low is
not a bug; it is what a growth scare DOES at a capitulation. But nothing labeled it, so the
extreme read like an unqualified "get out" beside a tape that was turning. This organ prints
one honest counter-read: when the growth scare is at an extreme AND a major index/cohort
simultaneously sits at a price-depth extreme, it is a "capitulation-zone reading —
historically two-sided" (a washout can precede a bounce as often as a further leg down).

DISPLAY / CONTEXT TIER (registration: research/ORACLE_WASHOUT_COUNTERREAD_REGISTRATION.md,
merged before any result is computed). All authority flags are False; the forward ledger is
pre-registered EXPECTED-NULL. It never ranks, gates, sizes, or escalates, and it NEVER
suppresses the risk banner — it sits BESIDE it as context, the way the election-cycle
modulator does. Quiet (show=False) is the normal state; the chip appears only in the rare
co-occurrence. The word "validated" does not appear on these surfaces.

Two honest, separately-labeled depth inputs:
  • PRICE depth — trailing-63-session drawdown percentile vs a 10y self-history, computed
    from data/yahoo closes. Uniform semantic across SPY/QQQ/XLK (XLK is not in the IHM
    roster), and the literal "63d drawdown percentile" the masterplan named as the interim.
  • MOMENTUM depth (corroboration only) — IHM's washout_turn / low depth_pctile when
    data/index_momentum/latest.json is present. Labeled as momentum-histogram depth, never
    conflated with the price drawdown.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "washout_counterread.v1"

AUTHORITY: dict[str, Any] = {
    "tier": "display", "horizon_role": "context",
    "may_rank": False, "may_gate": False, "may_size": False, "may_escalate": False,
}
DISCLOSURE: str = (
    "Display-tier only. All may_* authority flags are False. It sits BESIDE the risk banner "
    "as context and never suppresses it. Forward ledger pre-registered as EXPECTED NULL — a "
    "capitulation-zone reading is historically TWO-SIDED (it precedes a bounce about as often "
    "as a further leg down); it is context, not a forecast, not a buy signal. Price depth = "
    "trailing-63-session drawdown percentile vs 10y self-history; momentum depth (if shown) = "
    "IHM MACD-histogram depth, a different quantity, labeled separately. The word 'validated' "
    "does not appear on these surfaces."
)

# thresholds (frozen in the registration doc; not tuned against outcomes)
GROWTH_EXTREME = 88.0        # risk-off band boundary (engine/risk_radar.py _DEFAULT_BANDS)
DD_PCT_EXTREME = 90.0        # current 63d drawdown in the deepest decile of its 10y history
DD_WINDOW = 63               # trailing sessions for the drawdown
DD_HIST_BARS = 252 * 10      # 10-year self-history for the percentile
DD_MIN_BARS = 252 * 3        # need >=3y before stating a percentile
IHM_DEPTH_PCT_LOW = 10.0     # IHM depth_pctile at/below this = momentum-depth extreme
PRICE_INDICES = ("SPY", "QQQ", "XLK")   # SPY/QQQ = broad; XLK = tech (not in IHM roster)
# the US growth scare is a US-market defensive-rotation read, so only US index/cohort depth
# corroborates it — an Asian index washout is irrelevant to whether it's a US capitulation.
IHM_US_ROSTER = ("SPY", "QQQ", "IWM", "SOXX", "MAG7")


def _data_dir() -> Path:
    return config.data_dir()


def _growth_from_regime() -> tuple[float | None, str | None, str | None]:
    """Read the current growth scare (score, band, asof) from data/regime/latest.json."""
    p = _data_dir() / "regime" / "latest.json"
    try:
        rr = json.loads(p.read_text()).get("risk_radar", {})
    except Exception:  # noqa: BLE001
        return None, None, None
    for s in rr.get("scares") or []:
        if s.get("scare") == "growth":
            return s.get("score"), s.get("band"), rr.get("asof")
    return None, None, rr.get("asof")


def dd_percentile(close: pd.Series) -> dict | None:
    """Current trailing-63-session drawdown and its percentile vs a 10y self-history of the
    same statistic (100 = deepest on record). None when history is too thin."""
    s = close.dropna()
    if len(s) < DD_MIN_BARS:
        return None
    roll_max = s.rolling(DD_WINDOW, min_periods=DD_WINDOW).max()
    dd = (s / roll_max - 1.0).dropna()           # <=0
    if len(dd) < DD_MIN_BARS:
        return None
    hist = dd.iloc[-DD_HIST_BARS:]
    cur = float(dd.iloc[-1])
    # depth percentile: share of history at least as SHALLOW as today (drawdown >= cur).
    # cur is the deepest (most negative) → almost all history is >= cur → depth_pctile ≈ 100;
    # a near-zero current drawdown → few history days are >= it → low depth_pctile.
    depth_pct = float((hist >= cur).mean() * 100.0)
    return {"drawdown_pct": round(cur * 100.0, 2), "depth_pctile": round(depth_pct, 1),
            "extreme": depth_pct >= DD_PCT_EXTREME, "n_hist": int(len(hist))}


def _price_depths(closes: dict[str, pd.Series]) -> list[dict]:
    out = []
    for sym in PRICE_INDICES:
        s = closes.get(sym)
        if s is None:
            continue
        d = dd_percentile(s)
        if d is None:
            continue
        out.append({"index": sym, "metric": "price_63d_drawdown_pctile", **d})
    return out


def _ihm_depths() -> list[dict]:
    """IHM momentum-histogram depth corroboration (labeled separately). Tolerant of absence."""
    p = _data_dir() / "index_momentum" / "latest.json"
    try:
        ihm = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for sym in IHM_US_ROSTER:
        node = (ihm.get("indices") or {}).get(sym)
        if not node:
            continue
        g = (node.get("grids") or {}).get("1D") or {}
        dp = g.get("depth_pctile")
        if dp is None:
            continue
        low_depth = float(dp) <= IHM_DEPTH_PCT_LOW
        washout_turn = any((e.get("quality_tag") == "washout_turn")
                           for e in (g.get("recent_events") or []))
        if low_depth or washout_turn:
            out.append({"index": sym, "metric": "ihm_macd_hist_depth_pctile",
                        "depth_pctile": round(float(dp), 1),
                        "reason": "low_depth" if low_depth else "washout_turn",
                        "washout_turn": bool(washout_turn), "extreme": True})
    return out


def compute(growth_score: float | None = None, growth_band: str | None = None,
            as_of: str | None = None, closes: dict[str, pd.Series] | None = None) -> dict:
    """The counter-read. `growth_score`/`growth_band` default to data/regime/latest.json.
    `closes` maps SPY/QQQ/XLK → close series (else loaded from data/yahoo). Returns a payload
    with show=True only when BOTH extremes co-occur. Pure w.r.t. its inputs; degrade-never-raise."""
    if growth_score is None:
        growth_score, growth_band, rd_asof = _growth_from_regime()
        as_of = as_of or rd_asof
    if closes is None:
        from lib import store
        closes = {}
        for sym in PRICE_INDICES:
            try:
                df = store.read("yahoo", sym)
                closes[sym] = df["close"] if df is not None and "close" in df else None
            except Exception:  # noqa: BLE001
                closes[sym] = None
    price = _price_depths({k: v for k, v in closes.items() if v is not None})
    price_hits = [d for d in price if d["extreme"]]
    ihm = _ihm_depths()                          # already filtered to extremes
    growth_extreme = growth_score is not None and float(growth_score) >= GROWTH_EXTREME
    # masterplan RC-R11: fire on growth-extreme AND a depth extreme on an index OR cohort,
    # via 63d price drawdown OR IHM washout_turn/low momentum-depth (the OR is why a
    # defensive-rotation scare on a shallow index pullback — 2026-06-26 — can still fire if
    # a cohort like MAG7/SOXX is washed out at the momentum grain).
    depth_hits = price_hits + ihm
    show = bool(growth_extreme and depth_hits)
    payload = {
        "schema": SCHEMA, "as_of": as_of, "show": show,
        "growth_score": round(float(growth_score), 1) if growth_score is not None else None,
        "growth_band": growth_band, "growth_extreme": growth_extreme,
        "price_depths": price, "price_hits": [d["index"] for d in price_hits],
        "ihm_depths": ihm, "ihm_hits": [d["index"] for d in ihm],
        "message_en": None, "message_zh": None,
        "authority": AUTHORITY, "disclaimer": DISCLOSURE,
    }
    if show:
        def _ihm_en(d):
            return (f"{d['index']} washout-turn (IHM)" if d["reason"] == "washout_turn"
                    else f"{d['index']} momentum-washed (IHM p{d['depth_pctile']:.0f})")
        def _ihm_zh(d):
            return (f"{d['index']} 动量拐点洗盘（IHM）" if d["reason"] == "washout_turn"
                    else f"{d['index']} 动量深跌（IHM p{d['depth_pctile']:.0f}）")
        parts = [f"{d['index']} {d['drawdown_pct']:.0f}% off (63d p{d['depth_pctile']:.0f})"
                 for d in price_hits]
        parts += [_ihm_en(d) for d in ihm]
        detail = "; ".join(parts)
        payload["message_en"] = (
            f"Capitulation-zone reading — historically two-sided. Growth scare "
            f"{payload['growth_score']:.0f} (extreme) alongside a depth extreme: {detail}. "
            f"A washout can precede a bounce about as often as a further leg down.")
        zh_parts = [f"{d['index']} 回撤{d['drawdown_pct']:.0f}%（63日p{d['depth_pctile']:.0f}）"
                    for d in price_hits]
        zh_parts += [_ihm_zh(d) for d in ihm]
        payload["message_zh"] = (
            f"资本投降区读数——历史上双向。成长恐慌 {payload['growth_score']:.0f}（极端），"
            f"同时出现深度极值：{'；'.join(zh_parts)}。洗盘之后反弹与再下跌概率相当。")
    return payload
