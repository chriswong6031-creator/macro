"""China Market State — the CN_PROFILE for engine/market_state.py.

The blender, multi-timeframe tape, verdict/cap/flip logic and component formatter
all live in engine.market_state and are market-neutral. This module supplies only
the China-native pieces: the index tape set and the five conditions readers, which
map A-share data (engine/china_conditions.py's RORO + recession + drawdown gauges,
the QVIX/margin froth z-legs, the PBoC liquidity overlay, and the breadth percentile
injected by build_china) onto the same 0-100 leg shape.

DISPLAY-ONLY and honest about its gaps: China has no leading Risk Radar, no VIX term
structure (QVIX + margin froth stand in for the volatility regime), no HY credit
spread (PBoC liquidity + the slowdown gauge stand in for credit), and the downturn
gauges are uncalibrated — so CN_PROFILE applies NO hard verdict overrides; the read is
a transparent blend of what has already turned. Pure functions, never raise.
"""
from __future__ import annotations

from engine.market_state import (MarketProfile, _clamp, _component, _metric, _num)

# the broad A-share tape — Shanghai Composite, CSI 300 (the benchmark), Shenzhen Component
_CN_INDICES = (
    ("000001.SS", "Shanghai", "上证综指"),
    ("510300.SS", "CSI 300", "沪深300"),
    ("399001.SZ", "Shenzhen", "深证成指"),
)

# z in roughly [-2.5, 2.5] → a 0-1 leg score centred at 0.5
def _z_to_s01(z: float, span: float = 0.18) -> float:
    return _clamp(0.5 + z * span)


def _cn_risk(latest: dict) -> dict | None:
    """F2 — cross-asset risk appetite from the China RORO composite (9 causal-z legs)."""
    roro = (latest.get("conditions") or {}).get("roro") or {}
    state = roro.get("roro_state")
    if state is None:
        return None
    base = {"risk-on": 0.78, "neutral": 0.5, "risk-off": 0.22}.get(state, 0.5)
    legs = [l for l in (roro.get("legs") or []) if l.get("lean") in ("risk-on", "risk-off")]
    agree = None
    if legs:
        on = sum(1 for l in legs if l["lean"] == "risk-on")
        n = len(legs)
        base = _clamp(base + ((on - (n - on)) / n) * 0.12)        # net lean nudges the base
        agree = round(100 * max(on, n - on) / n)
    zh_state = {"risk-on": "风险偏好", "neutral": "中性", "risk-off": "避险"}.get(state, state)
    read_en = f"Cross-asset RORO {state}" + (f"; {agree}% of legs agree" if agree is not None else "")
    read_zh = f"跨资产 RORO {zh_state}" + (f"；{agree}% 信号同向" if agree is not None else "")
    comp = _num(roro.get("roro"))
    return _component(
        "risk", "Risk appetite", "风险偏好", base, read_en, read_zh,
        [_metric("RORO", "RORO", state),
         _metric("Legs agree", "信号同向", f"{agree}%" if agree is not None else None),
         _metric("Composite", "综合", f"{comp:+.2f}" if comp is not None else None)])


def _cn_vol(latest: dict) -> dict | None:
    """F3 — volatility & froth proxy. China has no VIX term structure, so the QVIX fear
    z-leg (already negated → higher = calmer) and the margin-froth z-leg stand in."""
    roro = (latest.get("conditions") or {}).get("roro") or {}
    qz = _num(roro.get("china_roro_qvix"))        # negated z of QVIX300: + = calm
    mz = _num(roro.get("china_roro_margin"))       # negated margin-froth: + = de-crowding
    if qz is None and mz is None:
        return None
    num = den = 0.0
    if qz is not None:
        num += 0.62 * _z_to_s01(qz); den += 0.62
    if mz is not None:
        num += 0.38 * _z_to_s01(mz); den += 0.38
    s01 = _clamp(num / den) if den else None
    if s01 is None:
        return None
    calm = qz is not None and qz >= 0
    read_en = f"QVIX fear {'calm' if calm else 'elevated'}"
    read_zh = f"QVIX 恐慌{'平静' if calm else '升高'}"
    if mz is not None:
        read_en += "; margin froth " + ("easing" if mz >= 0 else "crowded")
        read_zh += "；融资" + ("降温" if mz >= 0 else "拥挤")
    return _component(
        "vol", "Volatility & froth", "波动与拥挤", s01, read_en, read_zh,
        [_metric("QVIX z", "QVIX z", f"{qz:+.2f}" if qz is not None else None),
         _metric("Margin froth z", "融资拥挤 z", f"{mz:+.2f}" if mz is not None else None)])


def _cn_breadth(latest: dict) -> dict | None:
    """F4 — participation. Reads the % >200d-MA 5y percentile + divergence flag that
    build_china precomputes into conditions['breadth'] from the china_breadth frame."""
    b = (latest.get("conditions") or {}).get("breadth") or {}
    p = _num(b.get("above200_pctile"))
    if p is None:
        return None
    div = bool(b.get("div"))
    s01 = _clamp(p - (0.16 if div else 0.0))
    read_en = f"Breadth {int(p * 100)}%ile of 5y; " + ("a divergence vs price" if div else "confirming price")
    read_zh = f"广度处于五年 {int(p * 100)} 百分位；" + ("与价格背离" if div else "确认价格")
    return _component(
        "breadth", "Breadth & participation", "广度与参与", s01, read_en, read_zh,
        [_metric(">200d %ile", ">200日 百分位", f"{int(p * 100)}%"),
         _metric("Divergence", "背离", "yes" if div else "no")])


def _cn_liquidity(latest: dict) -> dict | None:
    """F5 — PBoC liquidity & credit. The PBoC stance overlay, nudged by the slowdown
    gauge (a high slowdown reads as effectively tighter credit). No HY OAS in China."""
    liq = latest.get("liquidity_overlay")
    if liq is None:
        return None
    base = {"expanding": 0.82, "neutral": 0.5, "contracting": 0.28}.get(liq, 0.5)
    rec = (latest.get("conditions") or {}).get("recession") or {}
    lab = rec.get("label")
    adj = {"low": 0.08, "elevated": 0.0, "high": -0.12}.get(lab, 0.0)
    s01 = _clamp(base + adj)
    zh_liq = {"expanding": "扩张", "neutral": "中性", "contracting": "收缩"}.get(liq, liq)
    read_en = f"PBoC liquidity {liq}" + (f"; slowdown {lab}" if lab else "")
    read_zh = f"央行流动性{zh_liq}" + (f"；经济放缓{ {'low': '低', 'elevated': '偏高', 'high': '高'}.get(lab, lab)}" if lab else "")
    return _component(
        "liquidity", "PBoC liquidity & credit", "央行流动性与信用", s01, read_en, read_zh,
        [_metric("PBoC liquidity", "央行流动性", liq),
         _metric("Slowdown gauge", "放缓指标", f"{int(_num(rec.get('score')))}/100" if _num(rec.get("score")) is not None else None),
         _metric("Slowdown band", "放缓区间", lab)])


def _cn_stress(latest: dict) -> dict | None:
    """F6 — downturn-risk guard from the (uncalibrated, display-only) China slowdown +
    drawdown-fragility gauges. China has no macro_risk / systemic_stress objects."""
    C = latest.get("conditions") or {}
    rec = C.get("recession") or {}
    dd = C.get("drawdown_risk") or {}
    rscore = _num(rec.get("score"))                # 0-100 slowdown
    band = dd.get("band")
    if rscore is None and band is None:
        return None
    risk_on = (1 - rscore / 100) if rscore is not None else 0.6
    dd_s = {"low": 0.85, "elevated": 0.5, "high": 0.25, "extreme": 0.1}.get(band, 0.6)
    s01 = _clamp(0.5 * risk_on + 0.5 * dd_s)
    rlab = rec.get("label")
    read_en = f"Slowdown {rlab or '—'}; drawdown-risk band {band or '—'}"
    read_zh = (f"经济放缓{ {'low': '低', 'elevated': '偏高', 'high': '高'}.get(rlab, rlab or '—') }"
               f"；回撤风险区间{ {'low': '低', 'elevated': '偏高', 'high': '高', 'extreme': '极高'}.get(band, band or '—') }")
    return _component(
        "stress", "Downturn-risk guard", "下行风险护栏", s01, read_en, read_zh,
        [_metric("Slowdown", "放缓", f"{int(rscore)}/100" if rscore is not None else None),
         _metric("Drawdown band", "回撤区间", band),
         _metric("Fragility", "脆弱度", f"{int(_num(dd.get('score')))}/100" if _num(dd.get("score")) is not None else None)])


CN_PROFILE = MarketProfile(
    key="cn",
    indices=_CN_INDICES,
    tape_noun_en="China indices", tape_noun_zh="A股指数",
    component_readers=(_cn_risk, _cn_vol, _cn_breadth, _cn_liquidity, _cn_stress),
    radar_override=None,                            # China has no validated leading radar (v1)
    overrides=frozenset(),                          # uncalibrated gauges → no hard verdict forcing
    caveat_en=("Display-only and lighter than the US read: China has no leading Risk Radar, no "
               "VIX term structure (QVIX + margin froth stand in), no HY credit spread, and the "
               "downturn gauges are uncalibrated. It reads what has already turned — context, not a forecast."),
    caveat_zh=("仅供展示，较美股版更轻量：A股没有领先的风险雷达、没有 VIX 期限结构（以 QVIX 与融资拥挤替代）、"
               "没有高收益信用利差，且下行指标未经校准。它读取的是已经转向的信号 — 是背景，而非预测。"),
)
