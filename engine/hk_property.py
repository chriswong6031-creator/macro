"""Hong Kong residential-property context — the Centaline CCL leaf (DISPLAY-ONLY).

Reads the weekly Centa-City Leading Index (CCL) collected into data/hk_property by
collectors/hk_property.py and turns it into a compact property-cycle read for the
HK dashboard + the LLM brief. Property is a major HK wealth / credit channel
(negative-equity, developer balance sheets, consumption), so it colours the regime
narrative — but it is NEVER scored into hk_axes / hk_regime / hk_playbook.

Degrades to None if the CCL feed is missing/stale (the collector is a fragile
single-host scrape), so the dashboard panel simply hides.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import store


def _pctile(s: pd.Series, v: float) -> int | None:
    s = s.dropna()
    if s.empty:
        return None
    return int(round((s <= v).mean() * 100))


def _series(s: pd.Series, last: int | None = 260, ndigits: int = 2) -> dict:
    s = s.dropna()
    if last is not None and not s.empty:
        s = s.iloc[-last:]
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "vals": [round(float(v), ndigits) for v in s]}


def _ccl_block() -> dict | None:
    """Centa-City Leading Index level + trend block, or None if absent."""
    df = store.read("hk_property", "ccl")
    if df is None or df.empty or "ccl" not in df.columns:
        return None
    s = df["ccl"].astype(float).dropna()
    if len(s) < 4:
        return None
    level = float(s.iloc[-1])
    # weekly index: ~13 weeks ≈ 1 quarter, ~52 weeks ≈ 1 year
    chg_13w = round(100 * (level / float(s.iloc[-14]) - 1), 1) if len(s) > 14 else None
    chg_52w = round(100 * (level / float(s.iloc[-53]) - 1), 1) if len(s) > 53 else None
    mass = None
    if "ccl_mass" in df.columns and not df["ccl_mass"].dropna().empty:
        mass = round(float(df["ccl_mass"].dropna().iloc[-1]), 2)
    return {
        "level": round(level, 2),
        "mass": mass,
        "chg_13w": chg_13w,
        "chg_52w": chg_52w,
        "pctile": _pctile(s, level),
        "asof": s.index[-1].strftime("%Y-%m-%d"),
        "chart": _series(s),
    }


def _regime(ccl: dict | None) -> dict:
    """Map the CCL trend onto an up/flat/down property-cycle label."""
    if not ccl:
        return {"pulse": None, "label_en": "unknown", "label_zh": "未知", "tone": "muted"}
    q = ccl.get("chg_13w")
    if q is None:
        return {"pulse": 0, "label_en": "no trend", "label_zh": "无趋势", "tone": "muted"}
    if q >= 1.5:
        return {"pulse": q, "label_en": "recovering", "label_zh": "回暖", "tone": "up"}
    if q <= -1.5:
        return {"pulse": q, "label_en": "deflating", "label_zh": "走弱", "tone": "down"}
    return {"pulse": q, "label_en": "flat / basing", "label_zh": "盘整", "tone": "flat"}


def property_view() -> dict | None:
    """Full view-model for the HK property panel (chart {dates,vals} for plotly)."""
    ccl = _ccl_block()
    if ccl is None:
        return None
    return {"ccl": ccl, "regime": _regime(ccl)}


def regime_context() -> dict | None:
    """Compact scalar snapshot for data/hk_regime/latest.json → the LLM brief.
    Degrade-never-raise; display/context only, never a scored signal."""
    v = property_view()
    if v is None:
        return None
    ccl, r = v["ccl"], v["regime"]
    return {
        "regime": r["label_en"], "pulse": r["pulse"],
        "ccl_level": ccl["level"],
        "ccl_chg_13w": ccl["chg_13w"],
        "ccl_chg_52w": ccl["chg_52w"],
        "ccl_pctile": ccl["pctile"],
        "asof": ccl["asof"],
        "note": "display/context only — HK residential property cycle, not a scored signal",
    }
