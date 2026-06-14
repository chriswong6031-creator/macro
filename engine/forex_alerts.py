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


def _path():
    return config.data_dir() / "forex" / "alerts.jsonl"


def compute_all_events(results: dict, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or config.load()["forex"]
    labels = _labels(cfg)
    out: list[dict] = []
    for pair, df in results.items():
        if pair == "_dollar":
            continue
        out += _pair_events(pair, df, labels.get(pair, {"label": pair, "base": pair}))
    out += dollar_events(results.get("_dollar"))
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


def rebuild(results: dict) -> list[dict]:
    events = compute_all_events(results)
    write_events(events)
    log.info("forex alerts: %d events, latest %s", len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]
