"""Commodity Vector alert engine. Mirrors engine/btc_alerts.py but PER ASSET
(gold/silver/oil/copper) plus market-wide commodity-complex regime events.

Two kinds of events, one schema:
- DAILY state-change events, derived deterministically from the per-asset signal
  history: residual SHOCK state (the headline commodity event — an exogenous bid
  or pressure), risk-regime flip, macro-driver tailwind/headwind flip, 12-month
  trend flip, momentum/structure flips, allocation steps, COT crowding, gold/
  silver value extremes, and the commodity-complex regime quadrant. Recomputing
  from history is idempotent.
- INTRADAY PRICE-SHOCK events from a SYMMETRIC price-only state machine per asset
  (normal -> shock -> extended -> stabilizing -> normal), firing on a move in
  EITHER direction (oil spikes up on war; gold/silver flush down). The intraday
  sentinel drives this live.

Event schema: {id, ts, source='commodity', asset, type, severity (high|medium|
  info), headline, detail, context{}, anchor}. id = commodity:asset:type:bucket:
  to_state, so the sentinel and the daily recompute dedup naturally.

Writes data/commodity/alerts.jsonl (newest first).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

LABEL = {"gold": "Gold", "silver": "Silver", "copper": "Copper", "oil": "Oil"}
UNIT = {"gold": "$/oz", "silver": "$/oz", "copper": "$/lb", "oil": "$/bbl"}

# Chinese siblings (Asia red=up convention is handled in CSS, not here — these are
# just translations). The site ships both languages inline (l-en/l-zh spans) and the
# active one shows; events carry headline_zh/detail_zh built at source (composed
# sentences can't be looked up after the fact). Mirrors engine/btc_alerts.py.
LABEL_ZH = {"gold": "黄金", "silver": "白银", "copper": "铜", "oil": "原油"}
UNIT_ZH = {"gold": "美元/盎司", "silver": "美元/盎司", "copper": "美元/磅", "oil": "美元/桶"}

# how to READ a residual shock per asset (from the calibration verdicts — stable facts)
SHOCK_READ = {
    "gold": "Historically PERSISTS (central-bank-style bids have carried forward).",
    "silver": "Washouts tend to bounce; upside shocks are noisier.",
    "copper": "Historically PERSISTS (structural demand carries forward).",
    "oil": "Historically FADES — war/supply premia mean-revert.",
}
SHOCK_READ_ZH = {
    "gold": "历史上会持续（央行式买盘往往延续）。",
    "silver": "急跌后往往反弹；上行冲击则更嘈杂。",
    "copper": "历史上会持续（结构性需求往往延续）。",
    "oil": "历史上会消退 — 战争/供给溢价均值回归。",
}

# every state-machine token -> Chinese (graceful EN fallback for anything unmapped)
STATE_ZH = {
    "bull": "看多", "bear": "看空", "neutral": "中性",
    "constructive": "向好", "broken": "破位",
    "up": "上升", "down": "下降", "flat": "走平",
    "tailwind": "顺风", "headwind": "逆风",
    "high_risk": "高风险", "low_risk": "低风险",
    "crowded_long": "多头拥挤", "crowded_short": "空头拥挤",
    "silver_cheap": "白银偏便宜", "silver_rich": "白银偏贵",
    "exogenous_bid": "外生买盘", "exogenous_pressure": "外生压力",
    "Reflation": "再通胀", "Stagflation": "滞胀", "Goldilocks": "理想增长",
    "Deflation-scare": "通缩担忧", "Neutral": "中性",
}


def _z(tok) -> str:
    """Token -> Chinese, falling back to the de-underscored English token."""
    return STATE_ZH.get(tok, str(tok).replace("_", " "))


def _ev(asset, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%dT%H:%M")
    a = asset or "complex"
    return {"id": f"commodity:{a}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "commodity", "asset": a, "type": type_, "severity": severity,
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


# --------------------------------------------------------------------------- #
# daily state-change events (per asset)
# --------------------------------------------------------------------------- #
def _asset_events(asset: str, df: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    lab, unit = LABEL[asset], UNIT[asset]
    lab_zh, unit_zh = LABEL_ZH[asset], UNIT_ZH[asset]
    close = df["close"]

    def px(ts):
        v = close.get(ts, float("nan"))
        return f"{lab} {v:,.2f} {unit}" if pd.notna(v) else lab

    def px_zh(ts):
        v = close.get(ts, float("nan"))
        return f"{lab_zh} {v:,.2f} {unit_zh}" if pd.notna(v) else lab_zh

    # residual SHOCK — the headline commodity signal
    if "shock_state" in df.columns:
        for ts, frm, to in _transitions(df["shock_state"]):
            if to == "normal":
                continue
            word = "exogenous bid" if to == "exogenous_bid" else "exogenous pressure"
            z = df["shock_z"].get(ts, float("nan"))
            out.append(_ev(asset, "residual_shock", ts, "high",
                           f"{lab}: {word} detected",
                           f"{lab} moved beyond what its macro drivers explain "
                           f"(shock z {z:+.1f}). {SHOCK_READ[asset]} {px(ts)}.",
                           {"shock_z": round(float(z), 2) if pd.notna(z) else None,
                            "state": to}, to,
                           headline_zh=f"{lab_zh}：检测到{_z(to)}",
                           detail_zh=f"{lab_zh}的走势超出其宏观驱动可解释的范围"
                           f"（冲击 z {z:+.1f}）。{SHOCK_READ_ZH[asset]} {px_zh(ts)}。"))

    # risk regime
    if "risk_regime" in df.columns:
        for ts, frm, to in _transitions(df["risk_regime"]):
            word = "Elevated" if to == "high_risk" else "Calm"
            ri = df["risk_index"].get(ts, float("nan"))
            out.append(_ev(asset, "risk_regime", ts, "high",
                           f"{lab} risk turned {word}",
                           f"Risk Index {'rose through' if to=='high_risk' else 'fell back below'} "
                           f"the threshold to {ri:.0f}. {px(ts)}.",
                           {"risk_index": round(float(ri)) if pd.notna(ri) else None}, to,
                           headline_zh=f"{lab_zh}风险转为{'升高' if to=='high_risk' else '平静'}",
                           detail_zh=f"风险指数{'上穿' if to=='high_risk' else '回落跌破'}"
                           f"阈值至 {ri:.0f}。{px_zh(ts)}。"))

    # macro driver tailwind/headwind
    if "driver_state" in df.columns:
        for ts, frm, to in _transitions(df["driver_state"]):
            if to == "neutral":
                continue
            sc = df["driver_score"].get(ts, float("nan"))
            out.append(_ev(asset, "driver_shift", ts, "medium",
                           f"{lab} macro backdrop turned {to}",
                           f"Driver axis {sc:+.2f} ({frm} → {to}).", {"driver_score": round(float(sc), 2)}, to,
                           headline_zh=f"{lab_zh}宏观背景转为{_z(to)}",
                           detail_zh=f"驱动因素轴 {sc:+.2f}（{_z(frm)} → {_z(to)}）。"))

    # 12-month trend flip
    if "ts_trend" in df.columns:
        for ts, frm, to in _transitions(df["ts_trend"]):
            if to == "flat":
                continue
            note = " (oil mean-reverts — read as contrarian)" if asset == "oil" else ""
            note_zh = "（原油均值回归 — 应作逆向解读）" if asset == "oil" else ""
            out.append(_ev(asset, "trend_flip", ts, "medium",
                           f"{lab} 12-month trend turned {to}",
                           f"Trailing-year time-series momentum flipped {frm} → {to}{note}. {px(ts)}.",
                           {"ts_trend": to}, to,
                           headline_zh=f"{lab_zh} 12 个月趋势转为{_z(to)}",
                           detail_zh=f"过去一年的时间序列动量翻转 {_z(frm)} → {_z(to)}{note_zh}。{px_zh(ts)}。"))

    # momentum & structure
    for col, type_, label, label_zh in [("momentum_state", "momentum", "Momentum", "动量"),
                                        ("structure_state", "structure", "Structure", "结构")]:
        if col in df.columns:
            for ts, frm, to in _transitions(df[col]):
                if to == "neutral":
                    continue
                out.append(_ev(asset, type_, ts, "medium",
                               f"{lab} {label.lower()} → {to}",
                               f"{label} state {frm} → {to}. {px(ts)}.", {}, to,
                               headline_zh=f"{lab_zh}{label_zh} → {_z(to)}",
                               detail_zh=f"{label_zh}状态 {_z(frm)} → {_z(to)}。{px_zh(ts)}。"))

    # allocation step
    if "alloc_optimal" in df.columns:
        for ts, frm, to in _transitions(df["alloc_optimal"]):
            pct = int(round(float(to) * 100))
            out.append(_ev(asset, "allocation", ts, "medium",
                           f"{lab} allocation → {pct}%",
                           f"Optimal strategy moved {int(float(frm)*100)}% → {pct}% (momentum × risk).",
                           {"alloc_pct": pct}, str(to),
                           headline_zh=f"{lab_zh}配置 → {pct}%",
                           detail_zh=f"最优策略从 {int(float(frm)*100)}% 调整为 {pct}%（动量 × 风险）。"))

    # COT crowding onset
    if "pos_state" in df.columns:
        for ts, frm, to in _transitions(df["pos_state"]):
            if to == "neutral":
                continue
            out.append(_ev(asset, "positioning", ts, "info",
                           f"{lab} COT {to.replace('_', ' ')}",
                           f"Speculative net positioning reached {to.replace('_',' ')} "
                           f"({df['pos_pctile'].get(ts, float('nan')):.0f}th %ile, 3y).", {}, to,
                           headline_zh=f"{lab_zh} COT {_z(to)}",
                           detail_zh=f"投机净持仓达到{_z(to)}"
                           f"（3 年期第 {df['pos_pctile'].get(ts, float('nan')):.0f} 百分位）。"))

    # gold/silver value extreme (metals)
    if "gsr_state" in df.columns:
        for ts, frm, to in _transitions(df["gsr_state"]):
            if to == "neutral":
                continue
            out.append(_ev(asset, "value", ts, "info",
                           f"{lab}: gold/silver ratio {to.replace('_', ' ')}",
                           f"GSR at {df['gsr_pctile'].get(ts, float('nan')):.0f}th %ile (3y) — "
                           f"{'silver cheap vs gold' if to=='silver_cheap' else 'silver rich vs gold'}.",
                           {}, to,
                           headline_zh=f"{lab_zh}：金银比{_z(to)}",
                           detail_zh=f"金银比处于 3 年期第 {df['gsr_pctile'].get(ts, float('nan')):.0f} 百分位 — "
                           f"{'白银相对黄金便宜' if to=='silver_cheap' else '白银相对黄金偏贵'}。"))
    return out


def daily_state_events(results: dict) -> list[dict]:
    out: list[dict] = []
    for asset, df in results.items():
        if asset == "_complex":
            continue
        out += _asset_events(asset, df)
    cx = results.get("_complex")
    if cx is not None and "complex_regime" in cx.columns:
        for ts, frm, to in _transitions(cx["complex_regime"]):
            sev = "high" if to in ("Reflation", "Deflation-scare") else "medium"
            out.append(_ev(None, "complex_regime", ts, sev,
                           f"Commodity complex → {to}",
                           f"The dollar × growth quadrant shifted {frm} → {to}.", {}, to,
                           headline_zh=f"大宗商品综合体 → {_z(to)}",
                           detail_zh=f"美元 × 增长象限从 {_z(frm)} 切换为 {_z(to)}。"))
    return out


def risk_extreme_events(results: dict, cfg: dict) -> list[dict]:
    lvl, ndays = cfg["risk_extreme_level"], cfg["risk_extreme_days"]
    out = []
    for asset, df in results.items():
        if asset == "_complex" or "risk_index" not in df.columns:
            continue
        hi = df["risk_index"] >= lvl
        streak = hi.groupby((~hi).cumsum()).cumsum()
        for ts in df.index[(streak == ndays).fillna(False)]:
            out.append(_ev(asset, "risk_extreme", ts, "info",
                           f"{LABEL[asset]}: capitulation watch",
                           f"Risk Index held ≥ {lvl} for {ndays} days — at sustained "
                           f"extremes the gauge is contrarian (near-capitulation).",
                           {"risk_index": round(float(df['risk_index'].get(ts)))}, "extreme",
                           headline_zh=f"{LABEL_ZH[asset]}：投降式抛售观察",
                           detail_zh=f"风险指数连续 {ndays} 天 ≥ {lvl} — 在持续极值处"
                           f"该指标为逆向信号（接近投降）。"))
    return out


# --------------------------------------------------------------------------- #
# intraday symmetric price-shock state machine (per asset)
# --------------------------------------------------------------------------- #
def shock_states(hourly: pd.DataFrame, asset: str, cfg: dict) -> pd.Series:
    f = cfg["shock"]
    close = hourly["close"]
    ret = close.pct_change()
    n = f["move_window_h"]
    sigma_n = ret.rolling(f["vol_window_h"]).std() * np.sqrt(n)
    rN = close.pct_change(n)
    r24 = close.pct_change(24)
    enter_pct = f["enter_pct"][asset] / 100
    ext_pct = f["extended_pct"][asset] / 100

    states, cur, quiet = [], "normal", 0
    for i in range(len(close)):
        sN, m, m24 = sigma_n.iloc[i], rN.iloc[i], r24.iloc[i]
        shock = pd.notna(sN) and sN > 0 and abs(m) > f["enter_sigma"] * sN and abs(m) > enter_pct
        big24 = pd.notna(m24) and abs(m24) > ext_pct
        acute = bool(shock or big24)
        if cur == "normal":
            if acute:
                cur, quiet = "shock", 0
        elif cur == "shock":
            if big24:
                cur = "extended"
            elif not acute:
                quiet += 1
                if quiet >= f["stabilize_quiet_h"]:
                    cur, quiet = "stabilizing", 0
            else:
                quiet = 0
        elif cur == "extended":
            if not acute:
                quiet += 1
                if quiet >= f["stabilize_quiet_h"]:
                    cur, quiet = "stabilizing", 0
            else:
                quiet = 0
        elif cur == "stabilizing":
            if acute:
                cur, quiet = "shock", 0
            else:
                quiet += 1
                if quiet >= f["normal_quiet_h"]:
                    cur, quiet = "normal", 0
        states.append(cur)
    return pd.Series(states, index=close.index, name="shock_state")


def shock_events(hourly: pd.DataFrame | None, asset: str, cfg: dict) -> list[dict]:
    if hourly is None or hourly.empty:
        return []
    states = shock_states(hourly, asset, cfg)
    close = hourly["close"]
    n = cfg["shock"]["move_window_h"]
    rN = close.pct_change(n)              # the move the state machine actually triggers on
    r24 = close.pct_change(24)            # broader context
    lab, unit = LABEL[asset], UNIT[asset]
    lab_zh, unit_zh = LABEL_ZH[asset], UNIT_ZH[asset]
    out = []
    for ts, frm, to in _transitions(states):
        if to == "normal":  # the all-clear is implied by 'stabilizing' — no card
            continue
        c = float(close.get(ts, float("nan")))
        mv = float(rN.get(ts, float("nan"))) * 100     # trigger move (Nh)
        c24 = float(r24.get(ts, float("nan"))) * 100
        # direction from the trigger move, falling back to 24h if the Nh move is NaN
        sign = mv if pd.notna(mv) and mv != 0 else c24
        direction = "up" if sign >= 0 else "down"
        ctx = {"price": round(c, 2), "chg_nh_pct": round(mv, 1) if pd.notna(mv) else None,
               "chg_24h_pct": round(c24, 1) if pd.notna(c24) else None,
               "direction": direction, "state": to}
        # emit 'stabilizing' too (as info) so its transition commits — keeps the
        # persisted sentinel state fresh and avoids missing a later re-entry into shock.
        dir_zh = "上行" if direction == "up" else "下行"
        if to == "stabilizing":
            out.append(_ev(asset, "price_shock", ts, "info",
                           f"{lab} price shock stabilizing",
                           f"{lab} {c:,.2f} {unit} — the acute move is settling.", ctx, to,
                           headline_zh=f"{lab_zh}价格冲击趋稳",
                           detail_zh=f"{lab_zh} {c:,.2f} {unit_zh} — 剧烈波动正在平息。"))
        else:
            word = "extended move" if to == "extended" else "price shock"
            word_zh = "延伸性波动" if to == "extended" else "价格冲击"
            sev = "high" if to == "extended" else "medium"
            out.append(_ev(asset, "price_shock", ts, sev,
                           f"{lab} intraday {word} ({direction})",
                           f"{lab} {c:,.2f} {unit} — an acute {direction} move "
                           f"({mv:+.1f}% / {n}h, {c24:+.1f}% / 24h).", ctx, to,
                           headline_zh=f"{lab_zh}日内{word_zh}（{dir_zh}）",
                           detail_zh=f"{lab_zh} {c:,.2f} {unit_zh} — 一次剧烈的{dir_zh}波动"
                           f"（{mv:+.1f}% / {n}小时，{c24:+.1f}% / 24小时）。"))
    return out


# --------------------------------------------------------------------------- #
# build / load
# --------------------------------------------------------------------------- #
def _path():
    return config.data_dir() / "commodity" / "alerts.jsonl"


def compute_all_events(results: dict | None = None) -> list[dict]:
    cfg = config.load()["commodities"]["alerts"]
    if results is None:
        from engine import commodity_signals
        results = commodity_signals.compute_all()
    events = daily_state_events(results) + risk_extreme_events(results, cfg)
    for asset in LABEL:
        events += shock_events(store.read("commodity", f"{asset}_hourly"), asset, cfg)
    existing = load_events()
    by_id = {e["id"]: e for e in events}
    for e in existing:
        by_id.setdefault(e["id"], e)  # keep sentinel-only events; recompute wins on collision
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


def rebuild(results: dict | None = None) -> list[dict]:
    events = compute_all_events(results)
    write_events(events)
    log.info("commodity alerts: %d events, latest %s",
             len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]
