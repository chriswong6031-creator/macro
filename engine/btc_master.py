"""Bitcoin Vector — Master Signal synthesis (the command-center layer).

This is a PRESENTATION/synthesis layer, NOT a new alpha claim. It fuses the axes
the rest of the engine already computes into ONE transparent regime read so the
dashboard can lead with a single glanceable verdict, and it builds the scannable
"Signal Board" (every axis -> its live state + tone + the MEASURED calibration
grade from data/vector/calibration.json + a sparkline).

Honesty (carried into the UI): short-horizon DIRECTION is a measured coin-flip;
the Master Score is the STRATEGIC regime tilt (a weighted mean of oriented axes,
+ = constructive / risk-on), and the tactical read is still the calibrated
forward-drawdown card. The weights are fixed and transparent — no fitting — and
each axis is oriented by its own published calibration sign, so this can only
re-present gate-passed signals, never manufacture edge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _f(v):
    """Coerce to float or None (NaN-safe)."""
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _tanh(x, scale=1.0):
    return float(np.tanh(x / scale))


def _spark(s: pd.Series | None, n: int = 60, w: int = 100, h: int = 26) -> str:
    """A normalized 'x,y x,y ...' polyline points string for an inline SVG sparkline
    (min..max over the trailing window; y inverted so higher = up). '' if no data."""
    if s is None:
        return ""
    v = pd.to_numeric(s, errors="coerce").dropna().tail(n)
    if len(v) < 3:
        return ""
    lo, hi = float(v.min()), float(v.max())
    rng = hi - lo
    pts = []
    for i, val in enumerate(v.to_numpy()):
        x = w * i / (len(v) - 1)
        y = h - (h * (val - lo) / rng) if rng else h / 2
        pts.append(f"{x:.1f},{y:.1f}")
    return " ".join(pts)


# --------------------------------------------------------------------------- #
# the oriented axes that feed the Master Score. Each entry:
#   key, weight, fn(last) -> (contribution in [-1,+1] or None, tone, state_en, state_zh)
# + = constructive / risk-ON. Weights are fixed (transparent, not fitted).
# --------------------------------------------------------------------------- #
def _tone(c: float | None) -> str:
    if c is None:
        return "neutral"
    return "bull" if c > 0.12 else ("bear" if c < -0.12 else "neutral")


def _map_state(c, up_en, up_zh, dn_en, dn_zh, mid_en="Neutral", mid_zh="中性"):
    if c is None:
        return ("—", "—")
    if c > 0.12:
        return (up_en, up_zh)
    if c < -0.12:
        return (dn_en, dn_zh)
    return (mid_en, mid_zh)


def _axes_contributions(last: pd.Series) -> list[dict]:
    """List of {key, label_en, label_zh, w, c, tone, state_en, state_zh} for every
    oriented axis that has data this row. The Master Score = weighted mean of `c`."""
    g = last.get
    out = []

    def add(key, le, lz, w, c, up=("Risk-on", "偏多"), dn=("Risk-off", "偏空"),
            mid=("Neutral", "中性")):
        if c is None:
            return
        c = float(np.clip(c, -1, 1))
        se, sz = _map_state(c, up[0], up[1], dn[0], dn[1], mid[0], mid[1])
        out.append({"key": key, "label_en": le, "label_zh": lz, "w": w, "c": c,
                    "tone": _tone(c), "state_en": se, "state_zh": sz})

    # --- trend / momentum core (DIRECTIONAL) --------------------------------
    add("momentum", "Momentum", "动量", 1.0, _f(g("momentum")),
        ("Bullish", "看多"), ("Bearish", "看空"))
    add("structure", "Structure", "结构", 0.6, _f(g("structure")),
        ("Constructive", "偏多"), ("Broken", "走坏"))
    imp = _f(g("impulse"))
    add("impulse", "Impulse", "脉冲", 0.7, None if imp is None else np.clip(imp, -1, 1),
        ("Accelerating", "加速"), ("Exhausting", "衰竭"))

    # --- risk / volatility (CONFIRMED as drawdown) --------------------------
    ri = _f(g("risk_index"))
    add("risk", "Risk Index", "风险指数", 1.0, None if ri is None else -np.clip((ri - 25) / 60, -1, 1),
        ("Calm", "平静"), ("Stressed", "承压"))
    ls = _f(g("leverage_stress"))
    add("leverage", "Leverage stress", "杠杆压力", 0.3, None if ls is None else -np.clip((ls - 50) / 50, -1, 1),
        ("Low", "低"), ("Crowded", "拥挤"))

    # --- fundamentals / liquidity / demand (CONFIRMED / DIRECTIONAL) --------
    bfi = _f(g("bfi"))
    add("bfi", "BFI fundamentals", "BFI 基本面", 0.9, None if bfi is None else np.clip((bfi - 50) / 50, -1, 1),
        ("Positive", "正向"), ("Negative", "负向"))
    add("macro", "Macro liquidity", "宏观流动性", 0.8, _f(g("macro_score")),
        ("Tailwind", "顺风"), ("Headwind", "逆风"))
    etfz = _f(g("etf_flow_z"))
    add("etf", "ETF flows", "ETF 资金流", 0.4, None if etfz is None else _tanh(etfz, 1.0),
        ("Accumulation", "吸筹"), ("Distribution", "派发"))
    stz = _f(g("stbl_growth_z"))
    add("stbl", "Stablecoin tide", "稳定币潮汐", 0.4, None if stz is None else _tanh(stz, 1.5),
        ("Expanding", "扩张"), ("Contracting", "收缩"))
    prem = _f(g("coinbase_premium_ema"))
    add("premium", "Coinbase premium", "Coinbase 溢价", 0.2,
        None if prem is None else -_tanh(prem - 0.4, 1.0),  # >1.5 FOMO top is contrarian-bearish
        ("Healthy demand", "健康需求"), ("Euphoric/absent", "亢奋/缺位"))

    # --- valuation / extremes (contrarian, EXTREMES-calibrated) -------------
    vs = g("valuation_state")
    vc = (1.0 if vs == "undervalued" else (-1.0 if vs == "overvalued" else 0.0)) if isinstance(vs, str) else None
    add("valuation", "Valuation", "估值", 0.7, vc, ("Undervalued", "低估"), ("Overvalued", "高估"))
    ex = g("market_extreme")
    exc = (1.0 if ex == "capitulation" else (-1.0 if ex == "euphoria" else 0.0)) if isinstance(ex, str) else None
    add("extreme", "Capitulation/euphoria", "投降/亢奋", 0.6, exc,
        ("Capitulation", "投降"), ("Euphoria", "亢奋"))
    rr = _f(g("reserve_risk"))
    rrp = _f(g("reserve_risk_pctile"))
    rrc = None
    if rr is not None:
        rrc = -1.0 if rr > 0.02 else (np.clip((50 - rrp) / 50, -1, 1) if rrp is not None else 0.0)
    add("reserve_risk", "Reserve Risk", "储备风险", 0.4, rrc,
        ("Accumulation", "累积"), ("Distribution top", "派发顶部"))

    # --- positioning / behaviour (contrarian context) ----------------------
    cz = _f(g("cot_z"))
    add("cot", "CME positioning", "CME 持仓", 0.3, None if cz is None else -_tanh(cz, 1.5),
        ("Clean", "干净"), ("Crowded long", "多头拥挤"))
    fz = _f(g("funding_z"))
    add("funding", "Perp funding", "永续资金费率", 0.3, None if fz is None else -_tanh(fz, 1.5),
        ("Crowded short", "空头拥挤"), ("Crowded long", "多头拥挤"))
    mes = g("miner_econ_state")
    mec = ({"capitulation": 0.6, "stress": 0.2, "healthy": 0.0, "euphoria": -0.5}.get(mes)
           if isinstance(mes, str) else None)
    add("miner", "Miner economics", "矿工经济", 0.3, mec,
        ("Capitulation (bottoming)", "投降（筑底）"), ("Euphoria", "亢奋"))
    hs = g("holder_state")
    hsc = ({"accumulation": 0.5, "neutral": 0.0, "distribution": -0.5}.get(hs)
           if isinstance(hs, str) else None)
    add("holders", "Holder spread (STH/LTH)", "持有者价差", 0.2, hsc,
        ("Accumulation", "累积"), ("Distribution", "派发"))
    at = g("attention_state")
    atc = ({"apathy": 0.4, "normal": 0.0, "mania": -0.6}.get(at) if isinstance(at, str) else None)
    add("attention", "Attention (Wikipedia)", "关注度", 0.2, atc,
        ("Apathy (bottoming)", "冷清（筑底）"), ("Mania (froth)", "狂热（过热）"))

    # --- cross-asset / cycle ------------------------------------------------
    ba = _f(g("beta_asym"))
    add("beta", "Conditional beta", "条件贝塔", 0.3, None if ba is None else _tanh(ba, 0.6),
        ("Limited downside", "下行受限"), ("Drawdown amplifier", "回撤放大"))
    cph = g("cphase_phase")
    cpc = (0.4 if cph == "markup" else (-0.4 if cph == "markdown" else 0.0)) if isinstance(cph, str) else None
    add("cycle", "Cycle phase", "周期相位", 0.3, cpc, ("Markup", "拉升"), ("Markdown", "下行"))
    return out


# grade lookup: signal column -> human band, from data/vector/calibration.json verdicts
_GRADE_KEYS = {
    "momentum": "momentum", "structure": "structure", "impulse": "impulse",
    "risk": "risk_index", "leverage": "leverage_stress", "bfi": "bfi",
    "macro": "macro_score", "etf": "etf_flow_z", "stbl": "stbl_growth_z",
    "premium": "coinbase_premium_ema", "valuation": "mvrv_z", "extreme": "nupl",
    "reserve_risk": "reserve_risk", "cot": "cot_z", "funding": "funding_z",
    "beta": "corr_spx", "cycle": "cycle_pct",
}


def _grade(key: str, calib: dict) -> str:
    """Short calibration grade for a board axis (CONFIRMED / DIRECTIONAL / EXTREMES /
    CONTEXT / NEW). NEW = a mastermind-upgrade axis not yet in the calibration table."""
    if key in ("miner", "holders", "attention", "taker"):
        return "NEW"
    sig = (calib or {}).get("signals", {})
    v = (sig.get(_GRADE_KEYS.get(key, ""), {}) or {}).get("verdict", "")
    if "CONFIRMED" in v:
        return "CONFIRMED"
    if "DIRECTIONAL" in v:
        return "DIRECTIONAL"
    if "EXTREMES" in v:
        return "EXTREMES"
    if v:
        return "CONTEXT"
    return ""


# Signal-board groups (display order) -> the axes within them + the sig column to spark
_BOARD = [
    ("Trend & Momentum", "趋势与动量",
     [("momentum", "momentum"), ("structure", "structure"), ("impulse", "impulse")]),
    ("Risk & Volatility", "风险与波动",
     [("risk", "risk_index"), ("leverage", "leverage_stress"),
      ("beta", "down_beta"), ("attention", "wiki_views_z")]),
    ("Valuation & Cycle", "估值与周期",
     [("valuation", "mvrv_z"), ("reserve_risk", "reserve_risk"),
      ("extreme", "extreme_score"), ("cycle", "cphase_pct"), ("miner", "hashprice_pctile")]),
    ("Demand & Flows", "需求与资金流",
     [("bfi", "bfi"), ("etf", "etf_flow_z"), ("stbl", "stbl_growth_z"),
      ("premium", "coinbase_premium_ema"), ("holders", "sth_lth_sopr_spread")]),
    ("Macro & Positioning", "宏观与持仓",
     [("macro", "macro_score"), ("cot", "cot_z"), ("funding", "funding_z")]),
]


def synthesize(sig: pd.DataFrame, calib: dict | None = None) -> dict:
    """Build the Master Signal: a weighted-mean regime score (-100..+100), its band,
    the top constructive/cautionary drivers, and the grouped Signal Board with grades +
    sparklines. Pure + NaN-safe — returns a usable dict even on a sparse row."""
    calib = calib or {}
    if sig is None or sig.empty:
        return {"ok": False}
    last = sig.iloc[-1]
    axes = _axes_contributions(last)
    by_key = {a["key"]: a for a in axes}

    wsum = sum(a["w"] for a in axes)
    raw = sum(a["c"] * a["w"] for a in axes) / wsum if wsum else 0.0
    # gentle non-linear stretch so a broad-but-mild consensus still reads off-center
    score = int(round(100 * float(np.tanh(raw * 1.6))))
    gauge = int(round((score + 100) / 2))

    if score >= 35:
        band, band_zh, tone = "STRONG RISK-ON", "强烈偏多", "bull"
    elif score >= 12:
        band, band_zh, tone = "RISK-ON", "偏多", "bull"
    elif score <= -35:
        band, band_zh, tone = "STRONG RISK-OFF", "强烈偏空", "bear"
    elif score <= -12:
        band, band_zh, tone = "RISK-OFF", "偏空", "bear"
    else:
        band, band_zh, tone = "NEUTRAL", "中性", "neutral"

    ranked = sorted(axes, key=lambda a: abs(a["c"] * a["w"]), reverse=True)
    drivers_pos = [a for a in ranked if a["c"] > 0.12][:4]
    drivers_neg = [a for a in ranked if a["c"] < -0.12][:4]
    n_bull = sum(1 for a in axes if a["tone"] == "bull")
    n_bear = sum(1 for a in axes if a["tone"] == "bear")

    board = []
    for ge, gz, items in _BOARD:
        rows = []
        for key, spark_col in items:
            a = by_key.get(key)
            if not a:
                continue
            rows.append({
                "key": key, "label_en": a["label_en"], "label_zh": a["label_zh"],
                "tone": a["tone"], "state_en": a["state_en"], "state_zh": a["state_zh"],
                "grade": _grade(key, calib),
                "spark": _spark(sig[spark_col]) if spark_col in sig.columns else "",
            })
        if rows:
            board.append({"group_en": ge, "group_zh": gz, "rows": rows})

    n_confirmed = sum(1 for grp in board for r in grp["rows"] if r["grade"] == "CONFIRMED")
    headline_en, headline_zh = _headline(band, drivers_pos, drivers_neg)
    return {
        "ok": True, "score": score, "gauge": gauge, "band": band, "band_zh": band_zh,
        "tone": tone, "drivers_pos": drivers_pos, "drivers_neg": drivers_neg,
        "n_bull": n_bull, "n_bear": n_bear, "n_axes": len(axes), "n_confirmed": n_confirmed,
        "board": board, "headline_en": headline_en, "headline_zh": headline_zh,
    }


def _headline(band: str, pos: list, neg: list) -> tuple[str, str]:
    """One honest sentence: the regime band + the strongest pull on each side."""
    def names(d, zh=False):
        return "、".join(a["label_zh"] for a in d) if zh else ", ".join(a["label_en"] for a in d)
    p, n = pos[:2], neg[:2]
    en = f"Strategic regime reads {band.replace('-', ' ').lower()}."
    zh = "战略格局："
    if p:
        en += f" Supported by {names(p)}."
        zh += f"支撑：{names(p, True)}。"
    if n:
        en += f" Held back by {names(n)}."
        zh += f"拖累：{names(n, True)}。"
    en += " Direction over days stays a coin-flip — the drawdown card leads tactically."
    zh += "数日方向仍接近抛硬币 — 战术上以回撤卡片为准。"
    return en, zh
