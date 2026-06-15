"""China property & fiscal view-model — DISPLAY / regime context only.

Pure pandas over the `china_property` store (+ the 512200 property ETF from the
`china` price store). Every function returns a plain-Python dict or ``None`` if its
source is missing, so scripts/build_china.py can render the panel without any
reachability or crash risk (charts are built in build_china).

This is a CONTEXT read, NOT a scored A-share signal: A-shares mean-revert and China
history is short/regime-unstable, so the property cycle is surfaced to inform the
regime narrative (and the LLM brief), never fed into the scored china_axes. See
research/DATA_SIGNAL_EXPANSION_2026.md #10.

Components:
  breadth       70-city NBS new-home diffusion (count rising − falling) + tier-1 lead
  climate       国房景气指数 (NBS real-estate climate composite, 100 = neutral)
  construction  rebar + iron-ore futures momentum (high-freq construction demand)
  cgb           China govt-bond curve — fiscal/duration read, the free stress proxy
  prop_etf      512200 property-ETF drawdown — developer-stress proxy (LGFV-free)
  regime        a descriptive property-cycle label (display-only diffusion vote)
"""
from __future__ import annotations

import pandas as pd

from lib import store


def _pctile(s: pd.Series, v: float) -> int | None:
    s = s.dropna()
    if s.empty:
        return None
    return int(round((s <= v).mean() * 100))


def _series(s: pd.Series, last: int | None = None, ndigits: int = 2) -> dict:
    """ISO-date + value arrays for a plotly line, optionally trimmed to a tail of rows."""
    s = s.dropna()
    if last is not None:
        s = s.tail(last)
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "vals": [round(float(v), ndigits) for v in s]}


def _mom_z(close: pd.Series, win: int = 63) -> tuple[float | None, float | None]:
    """Trailing 63-trading-day return (%) and its z-score vs the past year."""
    close = close.dropna()
    if len(close) < win + 30:
        return None, None
    r = (close.pct_change(win) * 100).dropna()
    ref = r.tail(252)
    z = (r.iloc[-1] - ref.mean()) / (ref.std() or 1.0)
    return round(float(r.iloc[-1]), 1), round(float(z), 2)


def _breadth_block() -> dict | None:
    hp = store.read("china_property", "home_price")
    if hp is None or hp.empty or "new_breadth" not in hp.columns:
        return None
    b = hp["new_breadth"].dropna()
    if b.empty:
        return None
    last = hp.iloc[-1]
    out = {
        "date": hp.index[-1].strftime("%Y-%m"),
        "new": int(last["new_breadth"]),
        "rising": int(last.get("new_rising") or 0),
        "falling": int(last.get("new_falling") or 0),
        "flat": int(last.get("new_flat") or 0),
        "cities": int(last.get("cities") or 0),
        "second": int(last["second_breadth"]) if pd.notna(last.get("second_breadth")) else None,
        "trend_6m": int(b.iloc[-1] - b.iloc[-7]) if len(b) > 7 else None,
        "pctile": _pctile(b, float(b.iloc[-1])),
        "chart": _series(b.tail(132), ndigits=0),          # ~11y diffusion line
    }
    for k, col in (("tier1_mom", "tier1_new_mom"), ("tier1_yoy", "tier1_new_yoy")):
        v = last.get(col)
        out[k] = round(float(v), 2) if pd.notna(v) else None
    return out


def _climate_block() -> dict | None:
    cl = store.read("china_property", "climate")
    if cl is None or cl.empty or "climate" not in cl.columns:
        return None
    s = cl["climate"].dropna()
    if s.empty:
        return None
    chg = cl["climate_chg"].dropna()
    last_chg = float(chg.iloc[-1]) if not chg.empty else 0.0
    return {
        "date": cl.index[-1].strftime("%Y-%m"),
        "level": round(float(s.iloc[-1]), 2),
        "chg": round(last_chg, 2),
        "trend": "rising" if last_chg > 0.02 else "falling" if last_chg < -0.02 else "flat",
        "chg_12m": round(float(s.iloc[-1] - s.iloc[-13]), 2) if len(s) > 13 else None,
        "chart": _series(s.tail(180), ndigits=2),
    }


def _construction_block() -> dict | None:
    rb = store.read("china_property", "rebar")
    io = store.read("china_property", "iron_ore")
    have = [(n, d) for n, d in (("rebar", rb), ("iron_ore", io))
            if d is not None and not d.empty and "close" in d.columns]
    if not have:
        return None
    out: dict = {}
    zs: list[float] = []
    for name, df in have:
        close = df["close"].dropna()
        mom, z = _mom_z(close)
        out[name] = round(float(close.iloc[-1]), 1)
        out[f"{name}_mom"] = mom
        out[f"{name}_z"] = z
        if z is not None:
            zs.append(z)
    out["demand_z"] = round(sum(zs) / len(zs), 2) if zs else None
    out["date"] = max(df.index[-1] for _, df in have).strftime("%Y-%m-%d")
    # a single 'construction demand' line = the two contracts rebased to 100 and averaged
    parts = []
    for _, df in have:
        c = df["close"].dropna().tail(504)
        if not c.empty:
            parts.append(c / c.iloc[0] * 100)
    if parts:
        idx = pd.concat(parts, axis=1).mean(axis=1).dropna()
        out["chart"] = _series(idx, ndigits=1)
    return out


def _cgb_block() -> dict | None:
    cgb = store.read("china_property", "cgb")
    if cgb is None or cgb.empty or "cgb_10y" not in cgb.columns:
        return None
    y10 = cgb["cgb_10y"].dropna()
    if y10.empty:
        return None
    slope = cgb["cgb_10y2y"].dropna() if "cgb_10y2y" in cgb.columns else pd.Series(dtype=float)
    return {
        "date": cgb.index[-1].strftime("%Y-%m-%d"),
        "y10": round(float(y10.iloc[-1]), 3),
        "y2": round(float(cgb["cgb_2y"].dropna().iloc[-1]), 3) if "cgb_2y" in cgb else None,
        "y30": round(float(cgb["cgb_30y"].dropna().iloc[-1]), 3) if "cgb_30y" in cgb else None,
        "slope": round(float(slope.iloc[-1]), 3) if not slope.empty else None,
        "chg_6m": round(float(y10.iloc[-1] - y10.iloc[-127]), 3) if len(y10) > 127 else None,
        "pctile": _pctile(y10, float(y10.iloc[-1])),          # low pctile = historically low yields
        "chart": _series(y10.tail(1260), ndigits=3),          # ~5y 10y CGB line
    }


def _prop_etf_block() -> dict | None:
    """512200 property ETF drawdown from its all-time high — the developer-stress
    proxy that replaces (paid, policy-administered) LGFV spreads."""
    df = store.read("china", "512200.SS")
    if df is None or df.empty or "close" not in df.columns:
        return None
    px = df["close"].dropna()
    if len(px) < 30:
        return None
    ath = px.cummax()
    dd = (px / ath - 1.0) * 100
    return {
        "date": px.index[-1].strftime("%Y-%m-%d"),
        "price": round(float(px.iloc[-1]), 3),
        "drawdown": round(float(dd.iloc[-1]), 1),
        "ath_date": px.idxmax().strftime("%Y-%m"),
        "chart": _series(dd.tail(750), ndigits=1),            # ~3y underwater curve
    }


# property-cycle pulse: a 3-leg diffusion vote (price breadth, climate, construction
# demand). Descriptive ONLY — labels a regime, never sizes a trade.
_LABELS = {
    -3: ("Deep contraction", "深度收缩"), -2: ("Contraction", "收缩"),
    -1: ("Cooling", "降温"), 0: ("Stabilizing", "筑底企稳"),
    1: ("Firming", "回暖初现"), 2: ("Recovery", "复苏"), 3: ("Broad recovery", "全面复苏"),
}


def _regime(breadth, climate, construction) -> dict:
    pulse, drivers = 0, []
    if breadth:
        v = breadth["new"]
        leg = 1 if v > 0 else -1 if v < 0 else 0
        pulse += leg
        drivers.append({"en": f"70-city breadth {v:+d} ({breadth['rising']}↑/{breadth['falling']}↓)",
                        "zh": f"70城价格宽度 {v:+d} ({breadth['rising']}↑/{breadth['falling']}↓)",
                        "sign": leg})
    if climate:
        leg = 1 if climate["chg"] > 0.02 else -1 if climate["chg"] < -0.02 else 0
        pulse += leg
        drivers.append({"en": f"climate {climate['level']:.1f} {climate['trend']}",
                        "zh": f"景气指数 {climate['level']:.1f} {'上行' if leg>0 else '下行' if leg<0 else '走平'}",
                        "sign": leg})
    if construction and construction.get("demand_z") is not None:
        dz = construction["demand_z"]
        leg = 1 if dz > 0.25 else -1 if dz < -0.25 else 0
        pulse += leg
        drivers.append({"en": f"construction demand z {dz:+.2f}",
                        "zh": f"建材需求 z {dz:+.2f}", "sign": leg})
    pulse = max(-3, min(3, pulse))
    en, zh = _LABELS[pulse]
    # nuance the label when the worst is clearly easing / fresh deterioration
    if breadth and breadth.get("trend_6m") is not None:
        t = breadth["trend_6m"]
        if pulse <= -1 and t >= 12:
            en, zh = en + " (easing)", zh + "（边际改善）"
        elif pulse >= 0 and t <= -12:
            en, zh = en + " (rolling over)", zh + "（转弱）"
    tone = ("neg" if pulse <= -2 else "warn" if pulse < 0 else "pos" if pulse >= 1 else "neutral")
    return {"pulse": pulse, "label_en": en, "label_zh": zh, "tone": tone, "drivers": drivers}


def property_view() -> dict | None:
    """Full view-model for the china.html "Property & Fiscal" panel (with chart
    {dates,vals} dicts that build_china renders to plotly)."""
    breadth = _breadth_block()
    climate = _climate_block()
    construction = _construction_block()
    cgb = _cgb_block()
    prop_etf = _prop_etf_block()
    if not any((breadth, climate, construction, cgb, prop_etf)):
        return None
    return {
        "breadth": breadth, "climate": climate, "construction": construction,
        "cgb": cgb, "prop_etf": prop_etf,
        "regime": _regime(breadth, climate, construction),
    }


def regime_context() -> dict | None:
    """Compact scalar snapshot for data/china_regime/latest.json → the LLM brief.
    No chart arrays; just the numbers the narrator may cite (degrade-never-raise)."""
    v = property_view()
    if v is None:
        return None
    b, c, k, cg, e = (v["breadth"], v["climate"], v["construction"], v["cgb"], v["prop_etf"])
    r = v["regime"]
    return {
        "regime": r["label_en"], "pulse": r["pulse"],
        "home_price_breadth": b["new"] if b else None,
        "home_price_breadth_6m_trend": b.get("trend_6m") if b else None,
        "climate_index": c["level"] if c else None,
        "climate_trend": c["trend"] if c else None,
        "construction_demand_z": k.get("demand_z") if k else None,
        "cgb_10y": cg["y10"] if cg else None,
        "cgb_10y2y_slope": cg.get("slope") if cg else None,
        "cgb_10y_chg_6m": cg.get("chg_6m") if cg else None,
        "property_etf_drawdown": e["drawdown"] if e else None,
        "note": "display/context only — A-shares mean-revert, not a scored signal",
    }
