"""Canada Market State — the CA_PROFILE for engine/market_state.py.

Mirrors engine/market_state_cn.py / _hk.py. Canada had no conditions layer, so
engine/canada_conditions.py builds one in the same shape (conditions.roro / recession /
drawdown_risk) and build_canada injects it; these readers then map it onto the six legs:
  - Risk      : the cross-asset overlay RORO (commodities / CAD / S&P / VIX / DXY)
  - Volatility: the VIX leg from the overlay (Canada's cross-asset fear gauge — no domestic
                vol index; VIX drives the TSX via the global beta)
  - Breadth   : the % >200d-MA 5y percentile (injected by build_canada)
  - Liquidity : the BoC policy-rate / curve liquidity overlay + the slowdown gauge
  - Downturn  : the (uncalibrated) slowdown + drawdown-fragility gauges

The broad-market tape uses the S&P/TSX Composite plus its two dominant pillars,
Financials and Energy (the TSX is heavily concentrated in them). DISPLAY-ONLY and
uncalibrated; no leading radar; no hard verdict overrides. Pure functions, never raise.
"""
from __future__ import annotations

from engine.market_state import (MarketProfile, _clamp, _component, _metric, _num,
                                 _radar_override_display)

# the broad TSX tape — the Composite plus its two structural pillars
_CA_INDICES = (
    ("^GSPTSE", "TSX Composite", "TSX 综合"),
    ("XFN.TO", "Financials", "金融"),
    ("XEG.TO", "Energy", "能源"),
)


def _z_to_s01(z: float, span: float = 0.18) -> float:
    return _clamp(0.5 + z * span)


def _ca_risk(latest: dict) -> dict | None:
    """F2 — cross-asset risk appetite from the commodity/CAD/BoC overlay (7 global legs)."""
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
    read_en = f"Cross-asset RORO {state}" + (f"; {agree}% of legs agree" if agree is not None else "")
    read_zh = f"跨资产 RORO {zh_state}" + (f"；{agree}% 信号同向" if agree is not None else "")
    comp = _num(roro.get("roro"))
    return _component(
        "risk", "Risk appetite", "风险偏好", base, read_en, read_zh,
        [_metric("RORO", "RORO", state),
         _metric("Legs agree", "信号同向", f"{agree}%" if agree is not None else None),
         _metric("Composite", "综合", f"{comp:+.2f}" if comp is not None else None)])


def _ca_vol(latest: dict) -> dict | None:
    """F3 — volatility. Canada has no domestic vol index; the VIX leg from the overlay
    (negated → higher = calmer) is the cross-asset fear gauge that drives the TSX."""
    roro = (latest.get("conditions") or {}).get("roro") or {}
    vz = _num(roro.get("ca_roro_vix"))             # negated z of VIX: + = calm
    if vz is None:
        return None
    s01 = _z_to_s01(vz, span=0.20)
    calm = vz >= 0
    read_en = f"VIX fear {'calm' if calm else 'elevated'} — Canada's cross-asset fear gauge"
    read_zh = f"VIX 恐慌{'平静' if calm else '升高'} — 加拿大的跨资产恐慌指标"
    return _component(
        "vol", "Volatility (VIX)", "波动率（VIX）", s01, read_en, read_zh,
        [_metric("VIX z", "VIX z", f"{vz:+.2f}")])


def _ca_breadth(latest: dict) -> dict | None:
    """F4 — participation. Reads the % >200d-MA 5y percentile + divergence flag that
    build_canada precomputes into conditions['breadth']."""
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


def _ca_liquidity(latest: dict) -> dict | None:
    """F5 — BoC liquidity & credit. The BoC policy-rate / curve liquidity overlay, nudged
    by the slowdown gauge (a high slowdown reads as effectively tighter)."""
    liq = latest.get("liquidity_overlay")
    if liq is None or liq == "unknown":
        return None
    base = {"expanding": 0.82, "neutral": 0.5, "contracting": 0.28}.get(liq, 0.5)
    rec = (latest.get("conditions") or {}).get("recession") or {}
    lab = rec.get("label")
    adj = {"low": 0.08, "elevated": 0.0, "high": -0.12}.get(lab, 0.0)
    s01 = _clamp(base + adj)
    zh_liq = {"expanding": "扩张", "neutral": "中性", "contracting": "收缩"}.get(liq, liq)
    read_en = f"BoC liquidity {liq}" + (f"; slowdown {lab}" if lab else "")
    read_zh = f"加央行流动性{zh_liq}" + (f"；经济放缓{ {'low': '低', 'elevated': '偏高', 'high': '高'}.get(lab, lab)}" if lab else "")
    return _component(
        "liquidity", "BoC liquidity & curve", "加央行流动性与曲线", s01, read_en, read_zh,
        [_metric("BoC liquidity", "加央行流动性", liq),
         _metric("Slowdown gauge", "放缓指标", f"{int(_num(rec.get('score')))}/100" if _num(rec.get("score")) is not None else None),
         _metric("Slowdown band", "放缓区间", lab)])


def _ca_stress(latest: dict) -> dict | None:
    """F6 — downturn-risk guard from the (uncalibrated) Canada slowdown + drawdown gauges."""
    C = latest.get("conditions") or {}
    rec = C.get("recession") or {}
    dd = C.get("drawdown_risk") or {}
    rscore = _num(rec.get("score"))
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


CA_PROFILE = MarketProfile(
    key="ca",
    indices=_CA_INDICES,
    tape_noun_en="TSX segments", tape_noun_zh="TSX 板块",
    component_readers=(_ca_risk, _ca_vol, _ca_breadth, _ca_liquidity, _ca_stress),
    radar_override=_radar_override_display,         # external-driver radar (risk_radar_intl.CA, emerging)
    overrides=frozenset(),                          # uncalibrated gauges → no hard verdict forcing
    caveat_en=("Display-only and lighter than the US read: Canada has no leading Risk Radar and "
               "no domestic volatility index (the US VIX stands in for cross-asset fear), and the "
               "slowdown / drawdown gauges are newly built and uncalibrated. The TSX is heavily "
               "concentrated in financials, energy and materials, and globally driven. Context, not a forecast."),
    caveat_zh=("仅供展示，较美股版更轻量：加拿大没有领先的风险雷达、没有本土波动率指数（以美股 VIX 替代跨资产恐慌），"
               "放缓／回撤指标为新建且未经校准。TSX 高度集中于金融、能源与材料，且受全球驱动。是背景，而非预测。"),
)
