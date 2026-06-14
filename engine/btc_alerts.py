"""Bitcoin Vector alert engine.

Two kinds of events, one schema:
- DAILY state-change events, derived deterministically from the signal history
  (risk regime crossing 25, structure-shift trigger, momentum flip, allocation
  step, fundamentals zone, leadership rotation, market mode). Recomputing from
  history is idempotent — no stateful append needed.
- FLASH-CRASH events from a price-only state machine over hourly candles
  (normal -> flash_crash -> tail_risk_event -> stabilizing_price -> normal),
  which the intraday sentinel also drives live.

Event schema (richer than the macro feed; the home hub normalizes both):
  {id, ts, source='vector', type, severity (high|medium|info),
   headline, detail, context{}, anchor}

`id` = type:ts-bucket:to_state -> the sentinel and the daily recompute produce
the same id for the same transition, so they dedup naturally.

Writes data/vector/alerts.jsonl (full event log, newest first).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

ANCHOR = {"risk_regime": "#risk", "structure_shift": "#structure",
          "momentum_trigger": "#momentum", "allocation_change": "#allocation",
          "fundamentals": "#bfi", "leadership": "#crossasset",
          "market_mode": "#allocation", "risk_extreme": "#risk",
          "flash_crash": "#flash"}

# Chinese for the finite state-word vocabulary that gets interpolated into alert
# headlines/details (kept in step with engine/i18n.py's LEX). The site ships both
# languages in the DOM and toggles with CSS, so every alert carries a parallel
# `*_zh` string built at its source — composed sentences can't be looked up after
# the fact. Unknown words pass through unchanged (safe for tickers like BTC).
_ZH = {"High Risk": "高风险", "Low Risk": "低风险",
       "constructive": "偏多", "broken": "走坏", "neutral": "中性",
       "bull": "看多", "bear": "看空", "positive": "正向", "negative": "负向",
       "rising": "上升", "falling": "下降",
       "Strategic": "战略", "Tactical": "战术", "Alts": "山寨币", "BTC": "BTC"}


def _z(word: str) -> str:
    """Chinese for a finite-vocab state word, else the English itself."""
    return _ZH.get(word, _ZH.get(str(word).strip(), word))

# Conviction layer — every alert carries `tier` (act > watch > context, for
# prioritisation) plus `edge`/`forward` notes derived from the real backtest in
# data/vector/calibration.json: `signal` keys the verdict (CONFIRMED /
# DIRECTIONAL / EXTREMES / CONTEXT) and `whipsaw` keys the historical flip rate.
# This is the honesty fix — momentum/structure alerts get flagged "edge weakened
# post-2021", risk_index/bfi get "proven edge", so loud ≠ trustworthy by default.
# `tier` reflects actionability/time-horizon (a fast risk-off trigger outranks a
# slow fundamentals gauge) and is independent of `edge`/`severity`.
# NOTE: risk_extreme deliberately has signal=None — its contrarian-at-extremes
# thesis is the OPPOSITE of risk_index's measured directional verdict, so it must
# not borrow that "proven edge" label (it gets a bespoke honest note in _conviction).
CONVICTION = {
    "risk_regime":      {"tier": "act",     "signal": "risk_index", "whipsaw": "risk_regime"},
    "risk_extreme":     {"tier": "watch",   "signal": None,         "whipsaw": None},
    "flash_crash":      {"tier": "act",     "signal": None,         "whipsaw": None},
    "fundamentals":     {"tier": "watch",   "signal": "bfi",        "whipsaw": None},
    "structure_shift":  {"tier": "watch",   "signal": "structure",  "whipsaw": "structure_state"},
    "momentum_trigger": {"tier": "watch",   "signal": "momentum",   "whipsaw": "momentum_state"},
    "allocation_change":{"tier": "watch",   "signal": None,         "whipsaw": None},
    "market_mode":      {"tier": "context", "signal": None,         "whipsaw": "market_mode"},
    "leadership":       {"tier": "context", "signal": None,         "whipsaw": "alt_cycle_leader"},
}
_CALIB_CACHE: dict = {}


def _calib() -> dict:
    if "d" not in _CALIB_CACHE:
        try:
            p = config.data_dir() / "vector" / "calibration.json"
            _CALIB_CACHE["d"] = json.loads(p.read_text()) if p.exists() else {}
        except Exception:  # noqa: BLE001 — conviction is additive, never fatal
            _CALIB_CACHE["d"] = {}
    return _CALIB_CACHE["d"]


def _edge_from_verdict(v: str) -> str:
    if not v:
        return ""
    if v.startswith("CONFIRMED"):
        return "Proven edge — held up in both market halves."
    if v.startswith("DIRECTIONAL"):
        return "Lower conviction — the edge weakened after 2021 (ETF era)."
    if v.startswith("CONTEXT"):
        return "Context only — no measured forward-return edge."
    if v.startswith("EXTREMES"):
        return v  # the verdict text itself carries the measured base rates
    if v.startswith("INVERTED"):
        return "Inverted edge — historically moved opposite to the naive read."
    return v


def _edge_zh_from_verdict(v: str) -> str:
    """Chinese sibling of `_edge_from_verdict` (same branches)."""
    if not v:
        return ""
    if v.startswith("CONFIRMED"):
        return "经验证的优势 — 在市场的前后两半段均成立。"
    if v.startswith("DIRECTIONAL"):
        return "信心较低 — 该优势在 2021 年（ETF 时代）后减弱。"
    if v.startswith("CONTEXT"):
        return "仅作背景参考 — 无实测的前瞻收益优势。"
    if v.startswith("INVERTED"):
        return "反向优势 — 历史上与表面解读方向相反。"
    return v  # EXTREMES / unknown: keep the measured base-rate text verbatim


def _conviction(type_: str) -> dict:
    c = CONVICTION.get(type_, {"tier": "watch", "signal": None, "whipsaw": None})
    cal = _calib()
    edge, forward = "", ""
    edge_zh, forward_zh = "", ""
    sig = c["signal"]
    if sig:
        verdict = (cal.get("signals", {}).get(sig, {}) or {}).get("verdict", "")
        edge = _edge_from_verdict(verdict)
        edge_zh = _edge_zh_from_verdict(verdict)
    elif type_ == "allocation_change":
        opt = (cal.get("allocation", {}) or {}).get("optimal", {})
        if opt:
            edge = "Strategy output — beat buy-and-hold in backtest."
            edge_zh = "策略输出 — 在回测中跑赢买入并持有。"
            forward = (f"Backtest: {opt.get('cagr')}% CAGR vs {opt.get('hodl_cagr')}% "
                       f"buy-and-hold; max drawdown {opt.get('maxdd')}% vs "
                       f"{opt.get('hodl_maxdd')}%.")
            forward_zh = (f"回测：{opt.get('cagr')}% 年化 vs {opt.get('hodl_cagr')}% "
                          f"买入并持有；最大回撤 {opt.get('maxdd')}% vs "
                          f"{opt.get('hodl_maxdd')}%。")
    elif type_ == "risk_extreme":
        edge = ("Contrarian at sustained extremes — suggestive, not proven; "
                "high-risk bands show middling, regime-dependent forward returns.")
        edge_zh = ("持续极端时具逆向性 — 有提示意义但未经证实；"
                   "高风险区间的前瞻收益中等且依赖周期。")
    elif type_ == "flash_crash":
        edge = "Real-time risk event — act on it, don't wait for confirmation."
        edge_zh = "实时风险事件 — 应立即行动，无需等待确认。"
    wk = c["whipsaw"]
    if wk:
        w = (cal.get("whipsaw", {}) or {}).get(wk, {})
        if w.get("pct") is not None:
            note = f"Flips {w['pct']:.0f}% of the time historically (whipsaw rate)."
            forward = f"{forward} {note}".strip()
            note_zh = f"历史上约 {w['pct']:.0f}% 的时间会反转（来回波动率）。"
            forward_zh = f"{forward_zh} {note_zh}".strip()
    return {"tier": c["tier"], "edge": edge.strip(), "forward": forward.strip(),
            "edge_zh": edge_zh.strip(), "forward_zh": forward_zh.strip()}


def _ev(type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%dT%H:%M")
    conv = _conviction(type_)
    return {"id": f"{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "vector", "type": type_, "severity": severity,
            "headline": headline, "detail": detail, "context": context,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "anchor": ANCHOR.get(type_, ""),
            "tier": conv["tier"], "edge": conv["edge"], "forward": conv["forward"],
            "edge_zh": conv["edge_zh"], "forward_zh": conv["forward_zh"]}


# --------------------------------------------------------------------------- #
# daily state-change events
# --------------------------------------------------------------------------- #
def _transitions(state: pd.Series) -> list[tuple[pd.Timestamp, str, str]]:
    s = state.dropna()
    chg = s != s.shift()
    chg.iloc[0] = False
    return [(t, s.shift()[t], s[t]) for t in s.index[chg]]


def daily_state_events(sig: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    close = sig["close"]

    for ts, frm, to in _transitions(sig["risk_regime"]):
        word = "High Risk" if to == "high_risk" else "Low Risk"
        sev = "high"
        ri = sig["risk_index"].get(ts, float("nan"))
        px = close.get(ts, float('nan'))
        out.append(_ev("risk_regime", ts, sev,
                       f"Risk Off Signal changed to: {word}",
                       f"Risk Index crossed the 25 threshold to {ri:.0f} "
                       f"({'rising' if to=='high_risk' else 'falling'}). "
                       f"BTC ${px:,.0f}.",
                       {"risk_index": round(float(ri), 1) if pd.notna(ri) else None,
                        "price": round(float(close.get(ts, float('nan'))))}, to,
                       headline_zh=f"风险关闭信号变为：{_z(word)}",
                       detail_zh=f"风险指数突破 25 阈值至 {ri:.0f}"
                                 f"（{'上升' if to=='high_risk' else '下降'}）。"
                                 f"BTC ${px:,.0f}。"))

    for ts, frm, to in _transitions(sig["structure_state"]):
        if to == "constructive":
            head, sev, head_zh = "Structure Shift: Bullish trigger", "high", "结构转变：看多触发"
        elif to == "broken":
            head, sev, head_zh = "Structure Shift: Bearish trigger", "high", "结构转变：看空触发"
        else:
            head, sev, head_zh = "Structure Shift: neutral", "medium", "结构转变：中性"
        val = sig["structure"].get(ts, float("nan"))
        out.append(_ev("structure_shift", ts, sev, head,
                       f"Structure oscillator now {val:+.2f} ({frm} → {to}).",
                       {"structure": round(float(val), 2) if pd.notna(val) else None}, to,
                       headline_zh=head_zh,
                       detail_zh=f"结构振荡器现为 {val:+.2f}（{_z(frm)} → {_z(to)}）。"))

    for ts, frm, to in _transitions(sig["momentum_state"]):
        if to == "bull":
            head, sev, head_zh = "Momentum turned Bullish", "high", "动量转为看多"
        elif to == "bear":
            head, sev, head_zh = "Momentum turned Bearish", "high", "动量转为看空"
        else:
            head, sev, head_zh = "Momentum cooled to neutral", "medium", "动量降温至中性"
        m = sig["momentum"].get(ts, float("nan"))
        out.append(_ev("momentum_trigger", ts, sev, head,
                       f"Momentum score {m:+.2f} ({frm} → {to}); ±0.5 is the trigger band.",
                       {"momentum": round(float(m), 2) if pd.notna(m) else None}, to,
                       headline_zh=head_zh,
                       detail_zh=f"动量评分 {m:+.2f}（{_z(frm)} → {_z(to)}）；±0.5 为触发区间。"))

    alloc = sig["alloc_optimal"]
    for ts, frm, to in _transitions(alloc):
        pct = int(round(float(to) * 100))
        frm_pct = int(float(frm) * 100)
        out.append(_ev("allocation_change", ts, "medium",
                       f"Allocation changed to {pct}% BTC",
                       f"Optimal strategy moved {frm_pct}% → {pct}% BTC "
                       f"(momentum × risk grid).",
                       {"alloc_pct": pct}, str(to),
                       headline_zh=f"配置调整为 {pct}% BTC",
                       detail_zh=f"最优策略从 {frm_pct}% 调整为 {pct}% BTC（动量 × 风险网格）。"))

    if "bfi_zone" in sig.columns:
        for ts, frm, to in _transitions(sig["bfi_zone"]):
            sev = "medium" if to != "neutral" else "info"
            bfi = sig['bfi'].get(ts, float('nan'))
            out.append(_ev("fundamentals", ts, sev,
                           f"Fundamentals turned {to}",
                           f"BFI entered the {to} zone (40/60 bands); "
                           f"now {bfi:.0f}.",
                           {"bfi": round(float(bfi))}, to,
                           headline_zh=f"基本面转为{_z(to)}",
                           detail_zh=f"BFI 进入{_z(to)}区间（40/60 分界）；当前 {bfi:.0f}。"))

    if "market_mode" in sig.columns:
        for ts, frm, to in _transitions(sig["market_mode"]):
            out.append(_ev("market_mode", ts, "medium",
                           f"Market mode changed to {to}",
                           f"Trend efficiency shifted the regime {frm} → {to}.",
                           {}, to,
                           headline_zh=f"市场模式变为{_z(to)}",
                           detail_zh=f"趋势效率使周期从 {_z(frm)} 转为 {_z(to)}。"))

    if "alt_cycle_leader" in sig.columns:
        for ts, frm, to in _transitions(sig["alt_cycle_leader"]):
            out.append(_ev("leadership", ts, "info",
                           f"Leadership rotated to {to}",
                           f"Relative-strength leadership moved {frm} → {to}.",
                           {}, to,
                           headline_zh=f"领涨轮动至 {_z(to)}",
                           detail_zh=f"相对强弱领涨从 {_z(frm)} 转为 {_z(to)}。"))
    return out


def risk_extreme_events(sig: pd.DataFrame, cfg: dict) -> list[dict]:
    """A capitulation-watch when Risk Index holds high for N days — the
    documented contrarian-at-extremes use. One event per onset."""
    lvl, ndays = cfg["risk_extreme_level"], cfg["risk_extreme_days"]
    hi = (sig["risk_index"] >= lvl)
    streak = hi.groupby((~hi).cumsum()).cumsum()
    onset = (streak == ndays)
    out = []
    for ts in sig.index[onset.fillna(False)]:
        ri = sig['risk_index'].get(ts)
        out.append(_ev("risk_extreme", ts, "info",
                       "Capitulation watch: risk elevated",
                       f"Risk Index held ≥ {lvl} for {ndays} days "
                       f"(now {ri:.0f}). At sustained extremes "
                       f"the index is contrarian — historically near-capitulation.",
                       {"risk_index": round(float(ri))}, "extreme",
                       headline_zh="投降式抛售观察：风险升高",
                       detail_zh=f"风险指数连续 {ndays} 天保持 ≥ {lvl}"
                                 f"（当前 {ri:.0f}）。在持续极端水平时该指数具有逆向性"
                                 f" — 历史上接近投降式抛售。"))
    return out


# --------------------------------------------------------------------------- #
# flash-crash state machine (hourly, price-only)
# --------------------------------------------------------------------------- #
def flash_crash_states(hourly: pd.DataFrame, cfg: dict) -> pd.Series:
    f = cfg["flash"]
    close = hourly["close"]
    ret = close.pct_change()
    sigma6 = ret.rolling(f["vol_window_h"]).std() * np.sqrt(f["drop_window_h"])
    r6 = close.pct_change(f["drop_window_h"])
    r24 = close.pct_change(24)
    low24 = close.rolling(24).min()

    states = []
    cur = "normal"
    quiet = 0
    last_low = np.inf
    idx = close.index
    for i, ts in enumerate(idx):
        c = close.iloc[i]
        s6 = sigma6.iloc[i]
        shock = pd.notna(s6) and s6 > 0 and r6.iloc[i] < -f["enter_sigma"] * s6
        big6 = pd.notna(r6.iloc[i]) and r6.iloc[i] * 100 < f["enter_6h_pct"]
        big24 = pd.notna(r24.iloc[i]) and r24.iloc[i] * 100 < f["enter_24h_pct"]
        acute = (shock and big6) or big24
        new_low = c <= low24.iloc[i] * 1.0005 if pd.notna(low24.iloc[i]) else False

        if cur == "normal":
            if acute:
                cur, quiet, last_low = "flash_crash", 0, c
        elif cur == "flash_crash":
            if pd.notna(r24.iloc[i]) and r24.iloc[i] * 100 < f["tail_24h_pct"]:
                cur = "tail_risk_event"
            elif not new_low:
                quiet += 1
                if quiet >= f["stabilize_quiet_h"]:
                    cur, quiet = "stabilizing_price", 0
            else:
                quiet, last_low = 0, min(last_low, c)
        elif cur == "tail_risk_event":
            if not new_low:
                quiet += 1
                if quiet >= f["stabilize_quiet_h"]:
                    cur, quiet = "stabilizing_price", 0
            else:
                quiet, last_low = 0, min(last_low, c)
        elif cur == "stabilizing_price":
            if acute:
                cur, quiet, last_low = "flash_crash", 0, c
            else:
                quiet += 1
                if quiet >= f["normal_quiet_h"]:
                    cur, quiet = "normal", 0
        states.append(cur)
    return pd.Series(states, index=idx, name="flash_state")


def impulse_sign(hourly: pd.DataFrame, cfg: dict) -> pd.Series:
    ret = hourly["close"].pct_change()
    ema = ret.ewm(span=cfg["flash"]["impulse_window_h"], adjust=False).mean()
    return np.sign(ema)


def flash_events(hourly: pd.DataFrame | None, cfg: dict) -> list[dict]:
    if hourly is None or hourly.empty:
        return []
    states = flash_crash_states(hourly, cfg)
    imp = impulse_sign(hourly, cfg)
    close = hourly["close"]
    out = []
    STATE_WORD = {"flash_crash": "flash crash", "tail_risk_event": "tail risk event",
                  "stabilizing_price": "stabilizing price", "normal": "normal"}
    STATE_WORD_ZH = {"flash_crash": "闪崩", "tail_risk_event": "尾部风险事件",
                     "stabilizing_price": "价格企稳", "normal": "正常"}
    for ts, frm, to in _transitions(states):
        if to == "normal":
            continue  # don't alert the all-clear as its own card (implied by stabilizing)
        c = float(close.get(ts, float("nan")))
        c24 = float(close.shift(24).get(ts, float("nan")))
        chg = (c / c24 - 1) * 100 if pd.notna(c24) and c24 else float("nan")
        impulse = "positive" if imp.get(ts, 0) > 0 else "negative"
        impulse_zh = "为正" if imp.get(ts, 0) > 0 else "为负"
        sev = "high" if to in ("flash_crash", "tail_risk_event") else "medium"
        out.append(_ev("flash_crash", ts, sev,
                       f"Flash Crash Index changed to: {STATE_WORD[to]}",
                       f"BTC ${c:,.0f}, {chg:+.2f}% (24h). Impulse {impulse}.",
                       {"price": round(c), "chg_24h_pct": round(chg, 2),
                        "impulse": impulse, "state": to}, to,
                       headline_zh=f"闪崩指数变为：{STATE_WORD_ZH[to]}",
                       detail_zh=f"BTC ${c:,.0f}，{chg:+.2f}%（24 小时）。脉冲{impulse_zh}。"))
    return out


# --------------------------------------------------------------------------- #
# build / load
# --------------------------------------------------------------------------- #
def _path() -> "object":
    return config.data_dir() / "vector" / "alerts.jsonl"


def compute_all_events(sig: pd.DataFrame | None = None) -> list[dict]:
    cfg = config.load()["vector"]["alerts"]
    if sig is None:
        sig = store.read("vector", "signals")
        sig.index = pd.to_datetime(sig.index)
    events = daily_state_events(sig) + risk_extreme_events(sig, cfg)
    events += flash_events(store.read("coinbase", "btc_hourly"), cfg)
    # merge with any sentinel-appended events newer than what we can derive
    existing = load_events()
    by_id = {e["id"]: e for e in events}
    for e in existing:
        by_id.setdefault(e["id"], e)  # keep sentinel-only events; recompute wins on collision
    merged = sorted(by_id.values(), key=lambda e: e["ts"], reverse=True)
    for e in merged:  # backfill conviction + zh on older/sentinel events so the log is uniform
        if "tier" not in e or "edge_zh" not in e:
            conv = _conviction(e.get("type", ""))
            e.setdefault("tier", conv["tier"])
            e.setdefault("edge", conv["edge"])
            e.setdefault("forward", conv["forward"])
            e.setdefault("edge_zh", conv["edge_zh"])
            e.setdefault("forward_zh", conv["forward_zh"])
        # composed sentences can't be re-derived for old events -> fall back to EN
        e.setdefault("headline_zh", e.get("headline", ""))
        e.setdefault("detail_zh", e.get("detail", ""))
    return merged


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


def rebuild(sig: pd.DataFrame | None = None) -> list[dict]:
    events = compute_all_events(sig)
    write_events(events)
    log.info("vector alerts: %d events, latest %s",
             len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]
