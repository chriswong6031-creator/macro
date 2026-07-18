"""Forex Vector alert engine — DAILY state-change events (no intraday).

Mirrors engine/commodity_alerts.py's daily layer, per pair, from the forex signal
history. FX has no hourly feed in this repo, so there is NO intraday price-shock
state machine — only deterministic, idempotent daily events recomputed from the
signal frame's state columns:

  residual SHOCK (decoupling / intervention), risk-regime flip, idiosyncratic
  12-month trend flip, momentum / structure flips, COT crowding (when available),
  plus FX-specific events: CARRY INVERSION (the foreign-minus-US rate crossing
  zero) and a PEG-ZONE APPROACH (the quote entering an intervention watch band).
  Market-wide: the dollar-smile regime quadrant shifting.

Event schema matches commodity_alerts (id, ts, source='forex', asset=pair, type,
severity, headline/detail + _zh, context, anchor). Writes data/forex/alerts.jsonl.
All events are CONTEXT — see LIMITATIONS.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

STATE_ZH = {
    "bull": "看多", "bear": "看空", "neutral": "中性",
    "constructive": "向好", "broken": "破位", "up": "上升", "down": "下降", "flat": "走平",
    "high_risk": "高风险", "low_risk": "低风险",
    "crowded_long": "多头拥挤", "crowded_short": "空头拥挤",
    "exogenous_bid": "外生买盘", "exogenous_pressure": "外生压力",
    "outflow_stress": "外流压力", "inflow": "资金流入",
    "Risk-off haven bid": "避险买盘", "US growth premium": "美国增长溢价",
    "Global reflation": "全球再通胀", "US-specific stress": "美国自身风险", "Neutral": "中性",
}


def _z(tok) -> str:
    return STATE_ZH.get(tok, str(tok).replace("_", " "))


def _ev(pair, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%dT%H:%M")
    a = pair or "dollar"
    return {"id": f"forex:{a}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "forex", "asset": a, "type": type_, "severity": severity,
            "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": "#timeline"}


def _transitions(state: pd.Series):
    s = state.dropna()
    if s.empty:
        return []
    chg = s != s.shift()
    chg.iloc[0] = False
    return [(t, s.shift()[t], s[t]) for t in s.index[chg]]


def _labels(cfg: dict | None = None) -> dict:
    cfg = cfg or config.load()["forex"]
    # pair -> (display label, base ccy, invert) for headline/price composition
    LAB = {"EURUSD": "EUR/USD", "USDJPY": "USD/JPY", "GBPUSD": "GBP/USD", "AUDUSD": "AUD/USD",
           "USDCAD": "USD/CAD", "USDCHF": "USD/CHF", "USDMXN": "USD/MXN", "USDBRL": "USD/BRL",
           "USDCNH": "USD/CNH"}
    out = {}
    for p, meta in cfg["assets"].items():
        out[p] = {"label": LAB.get(p, p), "base": meta.get("base", p), "invert": meta.get("invert")}
    return out


def _pair_events(pair: str, df: pd.DataFrame, meta: dict) -> list[dict]:
    out: list[dict] = []
    lab, base = meta["label"], meta["base"]
    close = df["close"]

    def quote(ts):
        v = close.get(ts, float("nan"))
        if pd.isna(v):
            return lab
        q = (1.0 / v) if meta.get("invert") else v
        return f"{lab} {q:,.4f}"

    # residual SHOCK — decoupling / intervention / geopolitics
    if "shock_state" in df.columns:
        for ts, frm, to in _transitions(df["shock_state"]):
            if to == "normal":
                continue
            word = "exogenous bid" if to == "exogenous_bid" else "exogenous pressure"
            z = df["shock_z"].get(ts, float("nan"))
            out.append(_ev(pair, "residual_shock", ts, "high",
                           f"{lab}: {base} {word} detected",
                           f"{base} moved beyond what the dollar + rates explain (shock z {z:+.1f}) — "
                           f"possible intervention / flow / geopolitics. {quote(ts)}.",
                           {"shock_z": round(float(z), 2) if pd.notna(z) else None}, to,
                           headline_zh=f"{lab}：{base} 检测到{_z(to)}",
                           detail_zh=f"{base} 走势超出美元+利率可解释范围（冲击 z {z:+.1f}）— "
                           f"可能为干预/资金流/地缘。{quote(ts)}。"))

    # risk regime
    if "risk_regime" in df.columns:
        for ts, frm, to in _transitions(df["risk_regime"]):
            word, word_zh = ("Elevated", "升高") if to == "high_risk" else ("Calm", "平静")
            ri = df["risk_index"].get(ts, float("nan"))
            out.append(_ev(pair, "risk_regime", ts, "high",
                           f"{lab} risk turned {word}",
                           f"Risk Index {'rose through' if to=='high_risk' else 'fell back below'} "
                           f"its threshold to {ri:.0f}. {quote(ts)}.",
                           {"risk_index": round(float(ri)) if pd.notna(ri) else None}, to,
                           headline_zh=f"{lab} 风险转为{word_zh}",
                           detail_zh=f"风险指数{'上穿' if to=='high_risk' else '回落跌破'}阈值至 {ri:.0f}。{quote(ts)}。"))

    # idiosyncratic 12-month trend flip (on the dollar-orthogonalized residual)
    if "ts_trend" in df.columns:
        for ts, frm, to in _transitions(df["ts_trend"]):
            if to == "flat":
                continue
            out.append(_ev(pair, "trend_flip", ts, "medium",
                           f"{lab}: {base} 12-month trend turned {to}",
                           f"Idiosyncratic (ex-dollar) trailing-year momentum flipped {frm} → {to}. {quote(ts)}.",
                           {"ts_trend": to}, to,
                           headline_zh=f"{lab}：{base} 12个月趋势转为{_z(to)}",
                           detail_zh=f"特异（去美元）的过去一年动量翻转 {_z(frm)} → {_z(to)}。{quote(ts)}。"))

    # momentum & structure
    for col, type_, label, label_zh in [("momentum_state", "momentum", "Momentum", "动量"),
                                        ("structure_state", "structure", "Structure", "结构")]:
        if col in df.columns:
            for ts, frm, to in _transitions(df[col]):
                if to == "neutral":
                    continue
                out.append(_ev(pair, type_, ts, "medium",
                               f"{lab}: {base} {label.lower()} → {to}",
                               f"{label} state {frm} → {to}. {quote(ts)}.", {}, to,
                               headline_zh=f"{lab}：{base} {label_zh} → {_z(to)}",
                               detail_zh=f"{label_zh}状态 {_z(frm)} → {_z(to)}。{quote(ts)}。"))

    # COT crowding (when available)
    if "pos_state" in df.columns:
        for ts, frm, to in _transitions(df["pos_state"]):
            if to == "neutral":
                continue
            pct = df["pos_pctile"].get(ts, float("nan"))
            out.append(_ev(pair, "positioning", ts, "info",
                           f"{lab} COT {to.replace('_', ' ')}",
                           f"Speculative net positioning reached {to.replace('_',' ')} "
                           f"({pct:.0f}th %ile, 3y) — contrarian context.", {}, to,
                           headline_zh=f"{lab} COT {_z(to)}",
                           detail_zh=f"投机净持仓达到{_z(to)}（3年期第 {pct:.0f} 百分位）— 逆向背景。"))

    # FX-specific: CARRY INVERSION (foreign-minus-US rate crossing zero)
    if "carry_diff" in df.columns and df["carry_diff"].notna().any():
        sign = df["carry_diff"].apply(lambda v: "positive" if v > 0 else ("negative" if v < 0 else "flat"))
        for ts, frm, to in _transitions(sign):
            if to == "flat" or frm == "flat":
                continue
            cd = df["carry_diff"].get(ts, float("nan"))
            out.append(_ev(pair, "carry_flip", ts, "medium",
                           f"{lab}: carry on {base} turned {to}",
                           f"The {base}-minus-US short-rate differential crossed zero ({cd:+.2f}%): "
                           f"holding {base} now {'earns' if to=='positive' else 'pays'} carry.",
                           {"carry_diff": round(float(cd), 2)}, to,
                           headline_zh=f"{lab}：{base} 套息转为{'正' if to=='positive' else '负'}",
                           detail_zh=f"{base} 减美国短端利差穿越零轴（{cd:+.2f}%）：持有 {base} 现在"
                           f"{'获得' if to=='positive' else '支付'}套息。"))

    # FX-specific: PEG / intervention-zone approach
    peg = meta.get("peg") if isinstance(meta.get("peg"), dict) else None
    if peg and peg.get("kind") == "intervention" and peg.get("watch"):
        lo, hi = peg["watch"]
        q = (1.0 / close) if meta.get("invert") else close
        inzone = ((q >= lo) & (q <= hi)).map({True: "in_zone", False: "out"})
        for ts, frm, to in _transitions(inzone):
            if to != "in_zone":
                continue
            qv = q.get(ts, float("nan"))
            out.append(_ev(pair, "peg_approach", ts, "high",
                           f"{lab} entered the intervention watch zone",
                           f"{lab} at {qv:,.2f} entered the ~{lo:g}–{hi:g} MoF intervention watch band — "
                           f"conviction is capped and the move can reverse on official action.",
                           {"quote": round(float(qv), 2)}, "in_zone",
                           headline_zh=f"{lab} 进入干预观察区",
                           detail_zh=f"{lab} 报 {qv:,.2f}，进入约 {lo:g}–{hi:g} 的财务省干预观察带 — "
                           f"信心受限，官方行动可能逆转走势。"))

    # FX-specific: CNH offshore-vs-onshore basis stress / inflow
    if "cnh_basis_state" in df.columns:
        for ts, frm, to in _transitions(df["cnh_basis_state"]):
            if to == "neutral":
                continue
            bp = df["cnh_basis_bps"].get(ts, float("nan"))
            if to == "outflow_stress":
                out.append(_ev(pair, "cnh_basis", ts, "high",
                               f"{lab}: offshore CNH stress",
                               f"The offshore−onshore CNH basis widened to {bp:+.0f} bps — offshore yuan "
                               f"weaker than the onshore fix, a depreciation / capital-outflow signal.",
                               {"basis_bps": round(float(bp)) if pd.notna(bp) else None}, to,
                               headline_zh=f"{lab}：离岸人民币承压",
                               detail_zh=f"离岸−在岸人民币基差扩大至 {bp:+.0f} 基点 — 离岸弱于在岸中间价，贬值/资金外流信号。"))
            else:
                out.append(_ev(pair, "cnh_basis", ts, "info",
                               f"{lab}: offshore CNH inflow",
                               f"The offshore−onshore CNH basis fell to {bp:+.0f} bps — offshore yuan "
                               f"stronger than onshore (inflow / risk-on).",
                               {"basis_bps": round(float(bp)) if pd.notna(bp) else None}, to,
                               headline_zh=f"{lab}：离岸人民币资金流入",
                               detail_zh=f"离岸−在岸人民币基差降至 {bp:+.0f} 基点 — 离岸强于在岸（资金流入/偏好风险）。"))
    return out


def dollar_events(dollar: pd.DataFrame | None) -> list[dict]:
    if dollar is None or dollar.empty or "smile_regime" not in dollar.columns:
        return []
    out = []
    for ts, frm, to in _transitions(dollar["smile_regime"]):
        out.append(_ev(None, "smile_regime", ts, "high",
                       f"Dollar regime → {to}",
                       f"The dollar-smile quadrant (dollar direction × risk) shifted {frm} → {to}.",
                       {}, to,
                       headline_zh=f"美元格局 → {_z(to)}",
                       detail_zh=f"美元微笑象限（美元方向 × 风险）从 {_z(frm)} 切换为 {_z(to)}。"))
    return out


# --------------------------------------------------------------------------- #
# MSX-1 desk-level event types (additive)
# --------------------------------------------------------------------------- #

def desk_smile_regime_events(dollar: pd.DataFrame | None) -> list[dict]:
    """Smile-regime flip events — rebuilt historically from the full _dollar frame
    (same as dollar_events but under type 'smile_regime_flip' for downstream routing).
    Kept separate from the existing 'smile_regime' type to avoid id collisions."""
    if dollar is None or dollar.empty or "smile_regime" not in dollar.columns:
        return []
    out = []
    for ts, frm, to in _transitions(dollar["smile_regime"]):
        out.append(_ev(None, "smile_regime_flip", ts, "high",
                       f"Dollar smile flipped: {frm} → {to}",
                       f"The dollar-smile decomposition regime changed: {frm} → {to}. "
                       f"This shifts the structural USD bias — "
                       f"{'safe-haven bid active' if to == 'Risk-off haven bid' else 'see dollar desk for context'}.",
                       {"from": frm, "to": to}, to,
                       headline_zh=f"美元微笑翻转：{_z(frm)} → {_z(to)}",
                       detail_zh=f"美元微笑分解格局变化：{_z(frm)} → {_z(to)}。"
                       f"{'避险买盘启动。' if to == 'Risk-off haven bid' else '详见美元总台。'}"))
    return out


def desk_triple_red_events(dollar: pd.DataFrame | None, desk: dict | None) -> list[dict]:
    """Triple-red onset/clear: USD + equities + Treasuries all falling simultaneously.

    triple_red is a scalar snapshot (no historical series), so only emit for the
    current session and rely on dedup-by-id for idempotency.
    """
    if not desk:
        return []
    sm = desk.get("smile") or {}
    triple_red = sm.get("triple_red")
    if triple_red is None:
        return []
    # Use today's date as the event timestamp (scalar snapshot, not historical series)
    ts = pd.Timestamp.now(tz="UTC").normalize()
    to = "active" if triple_red else "clear"
    if triple_red:
        return [_ev(None, "triple_red", ts, "high",
                    "Triple-red: USD, equities, and Treasuries all declining",
                    "The dollar is not acting as a safe haven: USD, S&P 500, and "
                    "Treasuries (prices) have all fallen over the past month. "
                    "This is a potential stress-selling signal — watch for forced deleveraging.",
                    {"triple_red": True}, to,
                    headline_zh="三重下跌：美元、股市、国债同步下行",
                    detail_zh="美元未发挥避险功能：美元、标普500及美债（价格）过去一月均下跌。"
                    "警惕强制去杠杆风险。")]
    else:
        return [_ev(None, "triple_red", ts, "info",
                    "Triple-red cleared: safe-haven function may be restoring",
                    "The dollar, equities, and Treasuries are no longer all declining together. "
                    "The acute co-movement stress has eased.",
                    {"triple_red": False}, to,
                    headline_zh="三重下跌解除：避险功能可能恢复",
                    detail_zh="美元、股市、国债不再同步下跌，极端同向压力已缓解。")]


def desk_scenario_events(regime: dict | None) -> list[dict]:
    """Stress-scenario activation: emit current-day event when a scenario becomes active.

    Only the current snapshot is available (no historical activation series), so
    only current-day events are emitted; dedup-by-id keeps this idempotent.
    """
    if not regime or not regime.get("scenarios"):
        return []
    out = []
    ts = pd.Timestamp.now(tz="UTC").normalize()
    for s in regime["scenarios"]:
        if not s.get("active"):
            continue
        key = s.get("key", "unknown")
        name_en = s.get("name_en", key)
        name_zh = s.get("name_zh", key)
        intensity = s.get("intensity_today") or 0.0
        illus = s.get("illustrative", False)
        prob = s.get("prob") or {}
        p_cond = prob.get("p_cond")
        sev = "high" if intensity >= 60 else "medium"
        prob_txt = (f" Historical conditional frequency: {p_cond:.0%}."
                    if p_cond is not None else "")
        illus_note = " (Scenario is illustrative — history is limited.)" if illus else ""
        out.append(_ev(None, "scenario_active", ts, sev,
                       f"Stress scenario active: {name_en} ({intensity:.0f}%)",
                       f"The '{name_en}' scenario is active at {intensity:.0f}% intensity."
                       f"{prob_txt}{illus_note}",
                       {"key": key, "intensity": round(float(intensity), 1),
                        "illustrative": illus}, key,
                       headline_zh=f"压力情景激活：{name_zh}（{intensity:.0f}%）",
                       detail_zh=f"「{name_zh}」情景当前激活，强度 {intensity:.0f}%。"
                       f"{'历史条件频率：' + f'{p_cond:.0%}。' if p_cond is not None else ''}"
                       f"{'（情景为示意性 — 历史样本有限。）' if illus else ''}"))
    return out


def _path():
    return config.data_dir() / "forex" / "alerts.jsonl"


def compute_all_events(results: dict, cfg: dict | None = None,
                       desk: dict | None = None,
                       regime: dict | None = None) -> list[dict]:
    """Compute all FX alert events from signal frames + optional desk/regime context.

    MSX-1 additive: desk and regime are optional; existing callers without these
    args continue to work (all three new event generators degrade to [] when absent).
    """
    cfg = cfg or config.load()["forex"]
    labels = _labels(cfg)
    out: list[dict] = []
    for pair, df in results.items():
        if pair == "_dollar":
            continue
        out += _pair_events(pair, df, labels.get(pair, {"label": pair, "base": pair}))
    dol = results.get("_dollar")
    out += dollar_events(dol)
    # MSX-1: desk-level event types (additive)
    out += desk_smile_regime_events(dol)
    out += desk_triple_red_events(dol, desk)
    out += desk_scenario_events(regime)
    by_id = {e["id"]: e for e in out}
    existing = load_events()
    for e in existing:
        by_id.setdefault(e["id"], e)
    return sorted(by_id.values(), key=lambda e: e["ts"], reverse=True)


def write_events(events: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def load_events() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def rebuild(results: dict, desk: dict | None = None, regime: dict | None = None) -> list[dict]:
    """Rebuild alerts.jsonl deterministically from signal frames.

    MSX-1: desk and regime are optional keyword arguments so existing callers
    (test fixtures, manual invocations without desk/regime) continue to work.
    """
    events = compute_all_events(results, desk=desk, regime=regime)
    write_events(events)
    log.info("forex alerts: %d events, latest %s", len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]
