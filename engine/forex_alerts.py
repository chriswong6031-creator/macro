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

# Plain scenario names for bilingual headlines (B1.5 map)
SCENARIO_EN = {
    "carry_unwind": "Carry-trade unwind",
    "dollar_wrecking_ball": "Dollar squeeze",
    "em_crisis_capital_flight": "EM outflows",
    "haven_flight_risk_off": "Flight to safety",
    "reflation_risk_on": "Risk-on rally",
    "intervention_risk": "Intervention watch",
}
SCENARIO_ZH = {
    "carry_unwind": "套息平仓",
    "dollar_wrecking_ball": "美元挤压",
    "em_crisis_capital_flight": "新兴市场资金外流",
    "haven_flight_risk_off": "避险出逃",
    "reflation_risk_on": "风险偏好回升",
    "intervention_risk": "干预关注",
}

# Asset plain names for transmission_shift headlines (B1.5 map)
ASSET_EN = {
    "SPY": "US stocks", "EEM": "EM stocks", "GC=F": "Gold",
    "CL=F": "Oil", "HG=F": "Copper", "UST10": "US bonds (10y)", "BTC": "Bitcoin",
}
ASSET_ZH = {
    "SPY": "美股", "EEM": "新兴市场股票", "GC=F": "黄金",
    "CL=F": "原油", "HG=F": "铜", "UST10": "美债(10年)", "BTC": "比特币",
}

EFFECT_EN = {"headwind": "a headwind", "tailwind": "a tailwind", "neutral": "not linked now"}
EFFECT_ZH = {"headwind": "压制", "tailwind": "提振", "neutral": "暂无联动"}


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
            direction = "up" if to == "exogenous_bid" else "down"
            z = df["shock_z"].get(ts, float("nan"))
            out.append(_ev(pair, "residual_shock", ts, "high",
                           f"{lab}: Unusual move the dollar and rates don't explain ({direction})",
                           f"{base} moved beyond what the dollar + rates explain (shock z {z:+.1f}) — "
                           f"possible intervention / flow / geopolitics. {quote(ts)}.",
                           {"shock_z": round(float(z), 2) if pd.notna(z) else None}, to,
                           headline_zh=f"{lab}：出现美元与利率无法解释的异常{'上行' if direction == 'up' else '下行'}",
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
                if type_ == "momentum":
                    direction_word = "up" if to == "bull" else "down"
                    head_en = f"{lab}: Trend turned {direction_word}"
                    head_zh = f"{lab}：趋势转{'强' if direction_word == 'up' else '弱'}"
                elif type_ == "structure":
                    head_en = (f"{lab}: Chart shape {'turned constructive' if to == 'constructive' else 'broke down'}")
                    head_zh = (f"{lab}：形态转{'好' if to == 'constructive' else '弱'}")
                else:
                    head_en = f"{lab}: {base} {label.lower()} → {to}"
                    head_zh = f"{lab}：{base} {label_zh} → {_z(to)}"
                out.append(_ev(pair, type_, ts, "medium",
                               head_en,
                               f"{label} state {frm} → {to}. {quote(ts)}.", {}, to,
                               headline_zh=head_zh,
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


# Plain zone-word maps for dollar_events headlines (P2 — regime string only in tips)
_REGIME_ZONE_EN = {
    "Risk-off haven bid": "World stressed",
    "US growth premium": "US booming",
    "Global reflation": "Calm growth",
    "US-specific stress": "US wobble",
    "Neutral": "In between",
}
_REGIME_ZONE_ZH = {
    "Risk-off haven bid": "全球避险",
    "US growth premium": "美国强势",
    "Global reflation": "平静增长",
    "US-specific stress": "美国走弱",
    "Neutral": "中间地带",
}


def dollar_events(dollar: pd.DataFrame | None) -> list[dict]:
    if dollar is None or dollar.empty or "smile_regime" not in dollar.columns:
        return []
    out = []
    for ts, frm, to in _transitions(dollar["smile_regime"]):
        zone_en = _REGIME_ZONE_EN.get(to, to)
        zone_zh = _REGIME_ZONE_ZH.get(to, _z(to))
        out.append(_ev(None, "smile_regime", ts, "high",
                       f"Dollar regime → {zone_en}",
                       f"The dollar-smile quadrant (dollar direction × risk) shifted {frm} → {to}.",
                       {}, to,
                       headline_zh=f"美元格局 → {zone_zh}",
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


def _path():
    return config.data_dir() / "forex" / "alerts.jsonl"


def scenario_events(regime: dict, prev_active: set | None = None) -> list[dict]:
    """B1.2: scenario active/inactive transitions from the FX stress radar.

    M1: Include scenario key in event id to avoid id collisions across concurrent
    activations (previously every active scenario got id …:active, collapsing via dedup).
    M3: Only fire on membership EDGES: inactive→active (high) and active→inactive (info).
    Accepts prev_active set (wired from build_forex — same pattern as transmission_prev).
    """
    if not regime or not regime.get("scenarios"):
        return []
    out: list[dict] = []
    as_of_raw = regime.get("as_of")
    if not as_of_raw:
        return []
    try:
        ts = pd.Timestamp(as_of_raw)
    except Exception:
        return []

    prev = prev_active if prev_active is not None else set()
    now_active: set = set()

    for s in regime["scenarios"]:
        key = s.get("key", "")
        if not key:
            continue
        name_en = SCENARIO_EN.get(key, key.replace("_", " ").title())
        name_zh = SCENARIO_ZH.get(key, key)
        is_active = bool(s.get("active"))
        if is_active:
            now_active.add(key)

        was_active = key in prev

        # M3: fire ONLY on edges
        if is_active and not was_active:
            # inactive → active edge
            out.append(_ev("dollar", "scenario", ts, "high",
                           f"{name_en} pattern now active",
                           f"The {name_en.lower()} stress pattern crossed the activation threshold "
                           f"({s.get('n_fired', 0)}/{s.get('min_legs', 2)}+ legs firing, "
                           f"intensity {round(s.get('intensity_today') or 0)}%).",
                           {"scenario": key, "intensity": round(s.get("intensity_today") or 0)},
                           f"active:{key}",  # M1: include scenario key so concurrent activations keep distinct ids
                           headline_zh=f"{name_zh}压力情景已激活",
                           detail_zh=f"{name_zh}压力情景超过激活阈值（{s.get('n_fired', 0)}/{s.get('min_legs', 2)}+项触发，强度{round(s.get('intensity_today') or 0)}%）。"))
        elif was_active and not is_active:
            # active → inactive edge (deactivation)
            out.append(_ev("dollar", "scenario", ts, "info",
                           f"{name_en} pattern no longer active",
                           f"The {name_en.lower()} stress pattern fell below the activation threshold.",
                           {"scenario": key},
                           f"inactive:{key}",  # M1: distinct id per scenario
                           headline_zh=f"{name_zh}情景已解除",
                           detail_zh=f"{name_zh}压力情景已低于激活阈值。"))

    return out


def transmission_shift_events(transmission_today: dict, transmission_prev: dict) -> list[dict]:
    """B1.2: fire when an asset's effect or stability changes vs the prior day snapshot."""
    if not transmission_today or not transmission_prev:
        return []
    out: list[dict] = []
    rows_today = {r["key"]: r for r in transmission_today.get("rows", [])}
    rows_prev = {r["key"]: r for r in transmission_prev.get("rows", [])}
    try:
        ts = pd.Timestamp(transmission_today.get("as_of", datetime.now(timezone.utc).isoformat()))
    except Exception:
        ts = pd.Timestamp(datetime.now(timezone.utc))
    for key, row in rows_today.items():
        prev = rows_prev.get(key)
        if not prev:
            continue
        eff_now, eff_prev = row.get("effect"), prev.get("effect")
        stab_now, stab_prev = row.get("stability"), prev.get("stability")
        name_en = ASSET_EN.get(key, key)
        name_zh = ASSET_ZH.get(key, key)
        changed = False
        if eff_now and eff_prev and eff_now != eff_prev:
            changed = True
            eff_label_en = EFFECT_EN.get(eff_now, eff_now)
            eff_label_zh = EFFECT_ZH.get(eff_now, eff_now)
            out.append(_ev("dollar", "transmission_shift", ts, "medium",
                           f"Dollar link to {name_en} changed: now {eff_label_en}",
                           f"The {name_en} dollar-transmission effect shifted from {eff_prev} to {eff_now}.",
                           {"asset": key, "from": eff_prev, "to": eff_now},
                           f"effect_{key}_{eff_now}",  # M2: include asset key so concurrent shifts keep distinct ids
                           headline_zh=f"美元与{name_zh}的联动改变：现为{eff_label_zh}",
                           detail_zh=f"{name_zh}的美元传导效应从{EFFECT_ZH.get(eff_prev, eff_prev)}变为{eff_label_zh}。"))
        if stab_now and stab_prev and stab_now != stab_prev and not changed:
            out.append(_ev("dollar", "transmission_shift", ts, "medium",
                           f"Dollar link to {name_en}: stability changed to {stab_now}",
                           f"The {name_en} dollar-transmission stability shifted from {stab_prev} to {stab_now}.",
                           {"asset": key, "stab_from": stab_prev, "stab_to": stab_now},
                           f"stab_{key}_{stab_now}",  # M2: include asset key so concurrent shifts keep distinct ids
                           headline_zh=f"美元与{name_zh}的联动稳定性变为{stab_now}",
                           detail_zh=f"{name_zh}的美元传导稳定性从{stab_prev}变为{stab_now}。"))
    return out


def dollar_flash_events(dollar: pd.DataFrame | None) -> list[dict]:
    """B1.2: fire when the broad-dollar day z crosses >=2 (unusually large single-day move)."""
    if dollar is None or dollar.empty or "dollar_day_z" not in dollar.columns:
        return []
    out: list[dict] = []
    threshold = 2.0
    in_flash = (dollar["dollar_day_z"].abs() >= threshold).map(
        {True: "flash", False: "normal"})
    for ts, frm, to in _transitions(in_flash):
        if to != "flash":
            continue
        z = dollar["dollar_day_z"].get(ts, float("nan"))
        # m2: only include pct when roc is actually available — do NOT fabricate via z*0.5
        roc_ser = dollar.get("dollar_roc")
        roc = roc_ser.get(ts, float("nan")) if roc_ser is not None and not roc_ser.empty else float("nan")
        has_pct = pd.notna(roc)
        if has_pct:
            pct = round(float(roc) * 100, 1)
            sign = "+" if pct >= 0 else ""
            head_en = f"Unusually large dollar move today ({sign}{pct}%)"
            detail_en = (f"The broad-dollar moved {sign}{pct}% today (z={z:+.1f}), "
                         f"an unusually large single-day move.")
            head_zh = f"美元今日异常大幅波动（{sign}{pct}%）"
            detail_zh = f"广义美元今日波动{sign}{pct}%（z={z:+.1f}），属异常大幅单日走势。"
        else:
            # roc unavailable — omit the percentage number from the headline
            pct = None
            head_en = "Unusually large dollar move today"
            detail_en = (f"The broad-dollar made an unusually large single-day move "
                         f"(z={z:+.1f}).")
            head_zh = "美元今日异常大幅波动"
            detail_zh = f"广义美元今日出现异常大幅单日走势（z={z:+.1f}）。"
        out.append(_ev("dollar", "dollar_flash", ts, "high",
                       head_en, detail_en,
                       {"dollar_day_z": round(float(z), 2) if pd.notna(z) else None,
                        "pct": pct},
                       "flash",
                       headline_zh=head_zh,
                       detail_zh=detail_zh))
    return out



def compute_all_events(results: dict, cfg: dict | None = None,
                       desk: dict | None = None,
                       regime: dict | None = None,
                       transmission: dict | None = None,
                       transmission_prev: dict | None = None,
                       scenario_prev_active: set | None = None) -> list[dict]:
    """Compute all FX alert events from signal frames + optional desk/regime context.

    Union signature: all params are optional/None-safe so existing callers without
    desk/transmission/scenario args continue to work unchanged.

    Event families:
    - pair-level: residual_shock, risk_regime, trend_flip, momentum, structure,
                  positioning, carry_flip, peg_approach, cnh_basis
    - dollar-level: smile_regime (existing historical transitions)
    - MSX-1 desk-level: smile_regime_flip, triple_red (main's vetted forms)
    - B1.2 families: dollar_flash, scenario (edge-detected only — M3), transmission_shift

    M3: scenario_events uses edge detection (inactive→active / active→inactive) so
    it does NOT emit for every day a scenario remains active.  desk_scenario_events
    (per-active-day) is intentionally omitted — superseded by scenario_events.
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
    # MSX-1: desk-level event types (main's vetted forms, kept verbatim)
    out += desk_smile_regime_events(dol)
    out += desk_triple_red_events(dol, desk)
    # B1.2 new families (edge-detected / threshold-based; no per-day-active firing)
    out += dollar_flash_events(dol)
    if regime:
        out += scenario_events(regime, prev_active=scenario_prev_active)
    if transmission and transmission_prev:
        out += transmission_shift_events(transmission, transmission_prev)
    by_id = {e["id"]: e for e in out}
    existing = load_events()
    for e in existing:
        by_id.setdefault(e["id"], e)
    # Sort ts DESC across all assets (spec: "sorted ts-desc across assets")
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


def rebuild(results: dict, desk: dict | None = None, regime: dict | None = None,
            transmission: dict | None = None,
            transmission_prev: dict | None = None,
            scenario_prev_active: set | None = None) -> list[dict]:
    """Rebuild alerts.jsonl deterministically from signal frames.

    Union signature: desk and regime are optional (MSX-1); transmission/
    transmission_prev/scenario_prev_active are optional (B1.2 edge detection).
    Existing callers without any optional args continue to work unchanged.
    """
    events = compute_all_events(results, desk=desk, regime=regime,
                                transmission=transmission,
                                transmission_prev=transmission_prev,
                                scenario_prev_active=scenario_prev_active)
    write_events(events)
    log.info("forex alerts: %d events, latest %s", len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]
