"""Hong Kong Market State — the HK_PROFILE for engine/market_state.py.

Mirrors engine/market_state_cn.py: the blender, tape, verdict/flip logic live in
engine.market_state; this supplies the HK index tape + the five conditions readers,
mapping engine/hk_conditions.py's gauges onto the same 0-100 leg shape. HK's
conditions object has the SAME nesting as China (conditions.roro{roro_state, legs,
hk_roro_*}, conditions.recession{score,label}, conditions.drawdown_risk{score,band}),
so the risk / breadth / liquidity / stress readers are near-identical; the volatility
leg uses the VHSI (HK's own implied-vol fear gauge) plus HIBOR funding instead of
QVIX + margin froth.

DISPLAY-ONLY and honest about its gaps: HK has no leading Risk Radar, no VIX term
structure (VHSI stands in), and its downturn gauges are uncalibrated — so HK_PROFILE
applies NO hard verdict overrides. HK is also heavily globally driven (US/EM beta +
the HKD peg), which the RORO composite already captures. Pure functions, never raise.
"""
from __future__ import annotations

from engine.market_state import (MarketProfile, _clamp, _component, _metric, _num,
                                 _radar_override_display)

# the broad HK tape — Hang Seng, HSCEI (H-shares), HS TECH (3033.HK proxy)
_HK_INDICES = (
    ("^HSI", "Hang Seng", "恒生指数"),
    ("^HSCE", "HSCEI", "国企指数"),
    ("3033.HK", "HS TECH", "恒生科技"),
)


def _z_to_s01(z: float, span: float = 0.18) -> float:
    return _clamp(0.5 + z * span)


def _hk_risk(latest: dict) -> dict | None:
    """F2 — cross-asset risk appetite from the HK RORO composite (12 globally-coupled legs)."""
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
        base = _clamp(base + ((on - (n - on)) / n) * 0.12)
        agree = round(100 * max(on, n - on) / n)
    zh_state = {"risk-on": "风险偏好", "neutral": "中性", "risk-off": "避险"}.get(state, state)
    rs = latest.get("risk_state")                  # HK global overlay, for the popup
    read_en = f"Cross-asset RORO {state}" + (f"; {agree}% of legs agree" if agree is not None else "")
    read_zh = f"跨资产 RORO {zh_state}" + (f"；{agree}% 信号同向" if agree is not None else "")
    comp = _num(roro.get("roro"))
    return _component(
        "risk", "Risk appetite", "风险偏好", base, read_en, read_zh,
        [_metric("RORO", "RORO", state),
         _metric("Legs agree", "信号同向", f"{agree}%" if agree is not None else None),
         _metric("Global risk", "全球风险", rs),
         _metric("Composite", "综合", f"{comp:+.2f}" if comp is not None else None)])


def _hk_vol(latest: dict) -> dict | None:
    """F3 — volatility & funding. HK has no VIX term structure: the VHSI fear z-leg
    (negated → higher = calmer) and the HIBOR-funding z-leg stand in."""
    roro = (latest.get("conditions") or {}).get("roro") or {}
    vz = _num(roro.get("hk_roro_vhsi"))            # negated z of VHSI: + = calm
    hz = _num(roro.get("hk_roro_hibor"))           # negated z of 20d HIBOR Δ: + = funding easing
    if vz is None and hz is None:
        return None
    num = den = 0.0
    if vz is not None:
        num += 0.66 * _z_to_s01(vz); den += 0.66
    if hz is not None:
        num += 0.34 * _z_to_s01(hz); den += 0.34
    s01 = _clamp(num / den) if den else None
    if s01 is None:
        return None
    calm = vz is not None and vz >= 0
    read_en = f"VHSI fear {'calm' if calm else 'elevated'}"
    read_zh = f"VHSI 恐慌{'平静' if calm else '升高'}"
    if hz is not None:
        read_en += "; HIBOR funding " + ("easing" if hz >= 0 else "tightening")
        read_zh += "；HIBOR 资金" + ("宽松" if hz >= 0 else "收紧")
    return _component(
        "vol", "Volatility (VHSI)", "波动率（VHSI）", s01, read_en, read_zh,
        [_metric("VHSI z", "VHSI z", f"{vz:+.2f}" if vz is not None else None),
         _metric("HIBOR funding z", "HIBOR 资金 z", f"{hz:+.2f}" if hz is not None else None)])


def _hk_breadth(latest: dict) -> dict | None:
    """F4 — participation. Reads the % >50d-MA 5y percentile + divergence flag that
    build_hk precomputes into conditions['breadth'] (HK has no >200d series)."""
    b = (latest.get("conditions") or {}).get("breadth") or {}
    p = _num(b.get("above200_pctile"))             # injected: pct_above_50 5y percentile
    if p is None:
        return None
    div = bool(b.get("div"))
    s01 = _clamp(p - (0.16 if div else 0.0))
    read_en = f"Breadth (% >50d) {int(p * 100)}%ile of 5y; " + ("a divergence vs price" if div else "confirming price")
    read_zh = f"广度（>50日）处于五年 {int(p * 100)} 百分位；" + ("与价格背离" if div else "确认价格")
    return _component(
        "breadth", "Breadth & participation", "广度与参与", s01, read_en, read_zh,
        [_metric(">50d %ile", ">50日 百分位", f"{int(p * 100)}%"),
         _metric("Divergence", "背离", "yes" if div else "no")])


def _hk_liquidity(latest: dict) -> dict | None:
    """F5 — liquidity & flows. The HKMA/peg liquidity overlay (M2 + HKD-peg pressure +
    southbound), nudged by the slowdown gauge. No HY OAS in HK."""
    liq = latest.get("liquidity_overlay")
    if liq is None or liq == "unknown":
        return None
    base = {"expanding": 0.82, "neutral": 0.5, "contracting": 0.28}.get(liq, 0.5)
    rec = (latest.get("conditions") or {}).get("recession") or {}
    lab = rec.get("label")
    adj = {"low": 0.08, "elevated": 0.0, "high": -0.12}.get(lab, 0.0)
    s01 = _clamp(base + adj)
    zh_liq = {"expanding": "扩张", "neutral": "中性", "contracting": "收缩"}.get(liq, liq)
    peg = latest.get("peg_state")
    read_en = f"Liquidity {liq}" + (f"; slowdown {lab}" if lab else "")
    read_zh = f"流动性{zh_liq}" + (f"；经济放缓{ {'low': '低', 'elevated': '偏高', 'high': '高'}.get(lab, lab)}" if lab else "")
    return _component(
        "liquidity", "Liquidity & peg flows", "流动性与联汇资金", s01, read_en, read_zh,
        [_metric("Liquidity", "流动性", liq),
         _metric("HKD peg", "港元联汇", peg),
         _metric("Slowdown band", "放缓区间", lab)])


def _hk_stress(latest: dict) -> dict | None:
    """F6 — downturn-risk guard from the (uncalibrated, display-only) HK slowdown +
    drawdown-fragility gauges. HK has no macro_risk / systemic_stress objects."""
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


HK_PROFILE = MarketProfile(
    key="hk",
    indices=_HK_INDICES,
    tape_noun_en="HK indices", tape_noun_zh="港股指数",
    component_readers=(_hk_risk, _hk_vol, _hk_breadth, _hk_liquidity, _hk_stress),
    radar_override=_radar_override_display,         # external-driver radar (risk_radar_intl.HK, recent-era)
    overrides=frozenset(),                          # uncalibrated gauges → no hard verdict forcing
    caveat_en=("Display-only and lighter than the US read: HK has no leading Risk Radar, no VIX "
               "term structure (VHSI stands in), and the downturn gauges are uncalibrated. HK is "
               "heavily globally driven — US/EM beta and the HKD peg. Context, not a forecast."),
    caveat_zh=("仅供展示，较美股版更轻量：港股没有领先的风险雷达、没有 VIX 期限结构（以 VHSI 替代），"
               "下行指标未经校准。港股高度受全球驱动 — 美股／新兴市场贝塔与港元联汇。是背景，而非预测。"),
)
