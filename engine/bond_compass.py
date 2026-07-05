"""Duration & Curve Compass — a transparent DIRECTIONAL read on US Treasuries.

ADDITIVE / leaf module, DISPLAY-ONLY. The rest of the board reads bonds health-
first; this leaf answers the question a trader actually asks — "lean long or short
duration, and steepener or flattener?" — by compositing the classic, literature-
grounded government-bond return factors, each shown transparently:

  • TREND   — time-series momentum on long-Treasury total return (Moskowitz-Ooi-
              Pedersen "century of trend"). + = price uptrend → bullish duration.
  • CARRY   — the curve slope (10y−3m) as carry + roll-down: a steep positive curve
              pays you to hold duration; an inverted curve is negative carry.
  • VALUE   — the real 10y yield rich/cheap vs its own 5y history (high real yield =
              cheap bonds = bullish; the 2022 negative-real-yield regime = expensive).
  • TERM-PREMIUM — the ACM 10y term premium percentile: a high term premium means
              you are paid to bear duration risk (bullish), a negative one is not.
  • MACRO IMPULSE — copper/gold + breakeven momentum as a growth/inflation reflation
              proxy; rising reflation is a duration HEADWIND (bearish).

The composite is an honest blend, NOT a tuned alpha model. The matching backtested
strategy (engine.strategies DURATION_TIMING, reports/duration-timing-phase0.md) found
the OOS edge of these factors is DRAWDOWN-CONTROL (MaxDD −18% vs −48% buy-and-hold),
with a MARGINAL deflated Sharpe — i.e. they tell you when to stand aside, not a
reliable return-timer. So this compass is positioning CONTEXT, never scored, never an
MRS leg. Each leg also feeds the bonds AI contract for the cross-asset brain.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_TY = 252
_DUR10 = 8.0   # approx modified duration of the 10y (for the carry/roll cushion)

# composite buckets on the [-1,1] lean
LEAN_LONG, LEAN_SHORT = 0.20, -0.20


def _pctile(s: pd.Series, window: int) -> float | None:
    s = s.dropna()
    if len(s) < max(60, window // 4):
        return None
    w = s.iloc[-window:]
    return float((w <= s.iloc[-1]).mean())


def _chg(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    v = s.iloc[-1] - s.iloc[-1 - n]
    return float(v) if np.isfinite(v) else None


def _z(s: pd.Series, window: int) -> float | None:
    s = s.dropna()
    if len(s) < max(60, window // 4):
        return None
    w = s.iloc[-window:]
    sd = w.std()
    return float((s.iloc[-1] - w.mean()) / sd) if sd and np.isfinite(sd) else None


def _state(v: float | None) -> str:
    if v is None:
        return "neutral"
    return "bullish" if v > 0.15 else ("bearish" if v < -0.15 else "neutral")


def _r(v, nd=2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _col(f: pd.DataFrame, name: str) -> pd.Series | None:
    if name not in f.columns or f[name].isna().all():
        return None
    return f[name].dropna()


# --- the legs (each returns a [-1,1] "lean long duration" value or None) -------
def _trend_leg(f: pd.DataFrame) -> float | None:
    from engine import total_return as tr
    from engine.cross_asset_trend import tsmom_alloc
    try:
        px = tr.long_treasury_tr()
    except Exception:  # noqa: BLE001
        return None
    if px is None or px.dropna().empty:
        return None
    a = tsmom_alloc(px).dropna()
    return float(a.iloc[-1]) if len(a) else None


def _carry_leg(f: pd.DataFrame) -> float | None:
    s = _col(f, "spread_10y3m")
    if s is None:
        return None
    p = _pctile(s, _TY * 5)
    return None if p is None else 2.0 * p - 1.0   # steep (high pctile) → bullish carry


def _value_leg(f: pd.DataFrame) -> float | None:
    s = _col(f, "us10y_real")
    if s is None:
        return None
    p = _pctile(s, _TY * 5)
    return None if p is None else 2.0 * p - 1.0   # high real yield → cheap → bullish


def _tp_leg(f: pd.DataFrame) -> float | None:
    s = _col(f, "term_premium_10y")
    if s is None:
        return None
    p = _pctile(s, _TY * 5)
    return None if p is None else 2.0 * p - 1.0   # high term premium → paid to hold → bullish


def _macro_leg(f: pd.DataFrame) -> float | None:
    """Reflation impulse = rising copper/gold + rising breakevens → bearish duration."""
    parts = []
    cg = _col(f, "copper_gold")
    if cg is not None:
        z = _z(cg.pct_change(63).dropna() * 100, _TY * 3)
        if z is not None:
            parts.append(z)
    be = _col(f, "breakeven_10y")
    if be is not None:
        c = _chg(be, 63)
        if c is not None:
            parts.append(c / 0.25)   # ~25bp/3m breakeven move ≈ 1 unit
    if not parts:
        return None
    impulse = float(np.tanh(np.mean(parts) / 1.5))
    return -impulse   # reflation up → bearish duration


_LEG_META = {
    "trend": ("Trend (TSMOM)", "趋势（时序动量）", 1.0,
              "Long-Treasury price momentum across 3/6/12-month horizons.",
              "长期国债价格在3/6/12个月窗口的时序动量。"),
    "carry": ("Carry & roll (10y−3m)", "套息与滚动（10年−3月）", 0.7,
              "A steep curve pays positive carry + roll-down to hold duration; inverted = negative carry.",
              "陡峭曲线为持有久期提供正套息+滚动收益；倒挂则为负套息。"),
    "value": ("Value (real-10y rich/cheap)", "价值（10年实际利率高/低）", 1.0,
              "High real yield = cheap bonds (good entry); negative real yield = expensive (the 2022 regime).",
              "实际利率高=债券便宜（入场良机）；负实际利率=昂贵（2022年情形）。"),
    "term_premium": ("Term premium", "期限溢价", 0.5,
                     "A high term premium means you're paid to bear duration risk; a negative one is not.",
                     "期限溢价高意味着持有久期风险有补偿；为负则没有。"),
    "macro": ("Macro impulse (reflation)", "宏观动能（再通胀）", 0.5,
              "Rising copper/gold + breakevens = reflation = a duration headwind.",
              "铜/金比与盈亏平衡通胀上行=再通胀=久期逆风。"),
}


def snapshot(f: pd.DataFrame) -> dict | None:
    if f is None or f.empty:
        return None
    raw = {"trend": _trend_leg(f), "carry": _carry_leg(f), "value": _value_leg(f),
           "term_premium": _tp_leg(f), "macro": _macro_leg(f)}
    legs, num, den = [], 0.0, 0.0
    for key, v in raw.items():
        meta = _LEG_META[key]
        if v is None:
            continue
        v = float(np.clip(v, -1, 1))
        num += v * meta[2]
        den += meta[2]
        legs.append({"key": key, "label_en": meta[0], "label_zh": meta[1],
                     "value": _r(v, 2), "weight": meta[2], "state": _state(v),
                     "note_en": meta[3], "note_zh": meta[4]})
    if not legs:
        return None
    lean = num / den if den else 0.0
    bucket = "lean_long" if lean > LEAN_LONG else ("lean_short" if lean < LEAN_SHORT else "neutral")
    signs = [np.sign(l["value"]) for l in legs if l["value"]]
    agree = float(np.mean([s == np.sign(lean) for s in signs])) if signs and lean else None

    snap = {
        "as_of": str(f.index[-1].date()),
        "duration": {
            "lean": _r(lean, 2), "bucket": bucket,
            "conviction": _r(abs(lean), 2), "agreement": _r(agree, 2),
            "n_legs": len(legs), "legs": legs,
        },
        "curve_trade": _curve_trade(f, raw),
        "expected": _expected_return(f),
    }
    snap["verdict_en"], snap["verdict_zh"] = _verdict(snap)
    snap["honest_en"] = ("Display-only positioning context, never scored. The same factors, backtested as a "
                         "long/flat duration timer (reports/duration-timing-phase0.md), earn their keep through "
                         "DRAWDOWN-CONTROL (MaxDD −18% vs −48% buy-and-hold), not reliable return-timing — the "
                         "deflated Sharpe is marginal. Read it as 'when to stand aside', not a trade signal.")
    snap["honest_zh"] = ("仅供仓位参考，从不评分。同样的因子作为多/空久期择时回测（见 reports/duration-timing-phase0.md），"
                         "其价值在于回撤控制（最大回撤 −18% 对比买入持有 −48%），而非可靠的收益择时——贬值夏普处于临界。"
                         "应理解为“何时退场”，而非交易信号。")
    return snap


def _curve_trade(f: pd.DataFrame, raw: dict) -> dict:
    """Steepener / flattener lean (display-only) from the policy-path + reflation reads."""
    s10y3m = _col(f, "spread_10y3m")
    slope = float(s10y3m.iloc[-1]) if s10y3m is not None and len(s10y3m) else None
    ntfs = None
    y1, y2, y3m = _col(f, "us1y"), _col(f, "us2y"), _col(f, "us3m")
    if y1 is not None and y2 is not None and y3m is not None:
        try:
            y15 = y1 + 0.50 * (y2 - y1)
            y175 = y1 + 0.75 * (y2 - y1)
            fwd = (y175 * 1.75 - y15 * 1.50) / 0.25
            ntfs = float((fwd - y3m).dropna().iloc[-1])
        except Exception:  # noqa: BLE001
            ntfs = None
    reflation = raw.get("macro")  # negative = reflation
    cuts_priced = ntfs is not None and ntfs < -0.10
    if cuts_priced and slope is not None and slope < 0.5:
        lean, en, zh = ("steepener",
                        "Cuts are priced while the curve is flat or inverted; the front end can lead yields lower.",
                        "市场已定价降息且曲线平坦/倒挂；短端可能率先下行。")
    elif reflation is not None and reflation < -0.25 and (slope is None or slope > 0):
        lean, en, zh = ("steepener",
                        "Reflation plus a positive curve points to long-end pressure.",
                        "再通胀叠加正向曲线，指向长端压力。")
    else:
        lean, en, zh = ("neutral",
                        "No clear steepener or flattener bias.",
                        "无明显陡峭或平坦倾向。")
    return {"lean": lean, "rationale_en": en, "rationale_zh": zh,
            "slope_10y3m": _r(slope), "ntfs": _r(ntfs)}


def _expected_return(f: pd.DataFrame) -> dict | None:
    """Rough 1y carry + roll-down for a 10y, and the 'cushion' — how far yields can
    rise before a buy-and-hold 10y loses money over the year. Honest approximation."""
    y10 = _col(f, "us10y")
    y7 = _col(f, "us7y")
    if y10 is None or len(y10) == 0:
        return None
    carry = float(y10.iloc[-1])
    roll = None
    if y7 is not None and len(y7):
        slope_per_yr = (float(y10.iloc[-1]) - float(y7.iloc[-1])) / 3.0  # 7y→10y per-maturity-year slope
        roll = _DUR10 * slope_per_yr   # rolldown ≈ duration × 1y slope (% price gain)
    carry_roll = carry + (roll or 0.0)
    cushion_bp = (carry_roll / _DUR10) * 100.0 if _DUR10 else None
    return {"carry_pct": _r(carry, 2), "rolldown_pct": _r(roll, 2),
            "carry_roll_pct": _r(carry_roll, 2), "cushion_bp": _r(cushion_bp, 0),
            "duration": _DUR10}


_BUCKET = {"lean_long": ("Lean long duration", "偏多久期"),
           "neutral": ("Neutral duration", "久期中性"),
           "lean_short": ("Lean short duration", "偏空久期")}


def _verdict(s: dict) -> tuple[str, str]:
    d = s["duration"]
    b_en, b_zh = _BUCKET.get(d["bucket"], (d["bucket"], d["bucket"]))
    exp = s.get("expected") or {}
    en = [f"{b_en} (lean {d['lean']:+.2f}, {int((d.get('agreement') or 0)*100)}% of legs agree)."]
    zh = [f"{b_zh}（倾向 {d['lean']:+.2f}，{int((d.get('agreement') or 0)*100)}% 分项一致）。"]
    ct = s.get("curve_trade") or {}
    if ct.get("lean") and ct["lean"] != "neutral":
        en.append(f"Curve: {ct['lean']} bias.")
        zh.append(f"曲线：偏{'陡峭' if ct['lean']=='steepener' else '平坦'}。")
    if exp.get("cushion_bp") is not None:
        en.append(f"Carry+roll ≈ {exp['carry_roll_pct']}%/yr; yields can rise ~{exp['cushion_bp']:.0f}bp "
                  f"before a 10y loses money over a year.")
        zh.append(f"套息+滚动约 {exp['carry_roll_pct']}%/年；收益率上行约 {exp['cushion_bp']:.0f}基点以内，"
                  f"10年期一年总回报仍不亏。")
    return " ".join(en), "".join(zh)
