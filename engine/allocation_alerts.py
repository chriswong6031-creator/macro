"""Narrative-Rotation alert engine — fires when the strategic playbook CHANGES, run over run.

Mirrors engine.theme_alerts (change-detection vs a persisted snapshot), but on the
engine.narrative_rotation output for a region: which themes enter/leave the suggested
book, leadership rotation, trend-gate gains/losses, the crash-overlay de-risk, and big
cash (risk on/off) swings. Per-region jsonl so each market has its own feed; the US feed
also flows into the site-wide Alert Center via engine.alert_triage (source 'rotation').

Event schema matches the other engines (id, ts, source='rotation', asset, type, severity,
headline/detail + _zh, context, anchor). First run seeds SILENTLY — no alert storm.
Display-only: the playbook is discipline, not a prediction.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 120


def _ev(region, asset, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"rotation:{region}:{asset}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "rotation", "region": region, "asset": asset, "type": type_,
            "severity": severity, "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": "#rotation"}


def _state_path(region):
    return config.data_dir() / "allocation" / f"state_{region}.json"


def _path(region):
    return config.data_dir() / "allocation" / f"alerts_{region}.jsonl"


def load_state(region) -> dict:
    p = _state_path(region)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def write_state(region, state: dict) -> None:
    p = _state_path(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def _snapshot(data: dict) -> dict:
    alloc = data.get("allocation") or {}
    rot = data.get("rotation") or {}
    held = [w["id"] for w in alloc.get("weights", [])]
    names = {w["id"]: w.get("name", w["id"]) for w in alloc.get("weights", [])}
    for r in data.get("ranks", []):
        names.setdefault(r["id"], r.get("name", r["id"]))
    eligible = sorted([r["id"] for r in data.get("ranks", []) if r.get("eligible")])
    return {"held": held, "names": names, "eligible": eligible,
            "leader": (rot.get("leader") or {}).get("id"),
            "cash": alloc.get("cash"), "crash": bool((alloc.get("crash_overlay") or {}).get("active"))}


def compute_events(data: dict, prior: dict | None, region: str) -> list[dict]:
    if not prior:
        return []
    ts = data.get("as_of")
    cur = _snapshot(data)
    nm = {**prior.get("names", {}), **cur["names"]}
    def name(bid):
        return nm.get(bid, bid)
    ev = []

    # --- book composition: themes entering / leaving the suggested allocation ---
    ph, ch = set(prior.get("held", [])), set(cur["held"])
    for bid in ch - ph:
        ev.append(_ev(region, bid, "entered_book", ts, "high",
                      f"➕ {name(bid)} entered the suggested book",
                      f"{name(bid)} is now one of the held themes in the {region.upper()} rotation book.",
                      {"to": "held"}, "in",
                      f"➕ {name(bid)} 进入建议组合",
                      f"{name(bid)} 现已纳入 {region.upper()} 轮动组合的持有主题。"))
    for bid in ph - ch:
        ev.append(_ev(region, bid, "left_book", ts, "high",
                      f"➖ {name(bid)} dropped out of the book",
                      f"{name(bid)} is no longer held in the {region.upper()} rotation book.",
                      {"to": "out"}, "out",
                      f"➖ {name(bid)} 移出建议组合",
                      f"{name(bid)} 已不在 {region.upper()} 轮动组合中。"))

    # --- leadership rotation ---
    if cur["leader"] and prior.get("leader") and cur["leader"] != prior.get("leader"):
        ev.append(_ev(region, cur["leader"], "leadership_rotation", ts, "medium",
                      f"🔄 New rotation leader: {name(cur['leader'])}",
                      f"{name(cur['leader'])} took rotation leadership from {name(prior['leader'])}.",
                      {"new": cur["leader"], "old": prior["leader"]}, "lead",
                      f"🔄 新轮动领涨：{name(cur['leader'])}",
                      f"{name(cur['leader'])} 取代 {name(prior['leader'])} 成为轮动领涨。"))

    # --- trend-gate gains / losses (eligibility flips) ---
    pe, ce = set(prior.get("eligible", [])), set(cur["eligible"])
    for bid in ce - pe:
        ev.append(_ev(region, bid, "gate_gained", ts, "medium",
                      f"📈 {name(bid)} reclaimed its trend",
                      f"{name(bid)} is back above its 200d trend — eligible for the book again.",
                      {"to": "eligible"}, "up",
                      f"📈 {name(bid)} 重回趋势上方",
                      f"{name(bid)} 重新站上 200 日趋势 — 再次具备入选资格。"))
    for bid in pe - ce:
        ev.append(_ev(region, bid, "gate_lost", ts, "medium",
                      f"📉 {name(bid)} lost its trend gate",
                      f"{name(bid)} fell below its 200d trend — out of the eligible set.",
                      {"to": "ineligible"}, "down",
                      f"📉 {name(bid)} 跌破趋势门",
                      f"{name(bid)} 跌破 200 日趋势 — 退出可选集合。"))

    # --- risk posture: crash de-risk + big cash swings (risk on/off) ---
    if cur["crash"] and not prior.get("crash"):
        ev.append(_ev(region, "book", "crash_derisk_on", ts, "high",
                      "🛑 Crash overlay ON — book halved to cash",
                      "The momentum-crash de-risk activated (bear tape + high vol): suggested book halved to cash.",
                      {"to": "on"}, "on",
                      "🛑 崩盘叠加启动 — 组合减半至现金",
                      "动量崩盘去风险已启动（熊市 + 高波动）：建议组合减半至现金。"))
    elif (not cur["crash"]) and prior.get("crash"):
        ev.append(_ev(region, "book", "crash_derisk_off", ts, "medium",
                      "✅ Crash overlay OFF — risk back on",
                      "The momentum-crash de-risk cleared; the book is no longer halved to cash.",
                      {"to": "off"}, "off",
                      "✅ 崩盘叠加解除 — 恢复风险敞口",
                      "动量崩盘去风险解除；组合不再减半至现金。"))
    pc, cc = prior.get("cash"), cur["cash"]
    if pc is not None and cc is not None and abs(cc - pc) >= 0.25:
        up = cc > pc
        ev.append(_ev(region, "book", "risk_shift", ts, "medium",
                      ("🔻 Risk dialed DOWN" if up else "🔺 Risk dialed UP") + f" — cash {round(pc*100)}% → {round(cc*100)}%",
                      f"The suggested cash weight moved from {round(pc*100)}% to {round(cc*100)}% (breadth/trend driven).",
                      {"from": pc, "to": cc}, "down" if up else "up",
                      ("🔻 降低风险" if up else "🔺 提高风险") + f" — 现金 {round(pc*100)}% → {round(cc*100)}%",
                      f"建议现金权重由 {round(pc*100)}% 变为 {round(cc*100)}%（广度/趋势驱动）。"))
    return ev


def load_events(region) -> list[dict]:
    p = _path(region)
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


def write_events(region, events: list[dict]) -> None:
    p = _path(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def recent(region, days: int = 45, as_of: str | None = None) -> list[dict]:
    evs = load_events(region)
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def rebuild(data: dict, region: str) -> list[dict]:
    """Diff vs prior state, append+dedup new events, persist new state. [] on the seed run."""
    if not data or not data.get("allocation"):
        return []
    prior = load_state(region)
    new = compute_events(data, prior, region)
    by_id = {e["id"]: e for e in load_events(region)}
    for e in new:
        by_id.setdefault(e["id"], e)
    merged = list(by_id.values())
    if merged:
        ref = max(pd.Timestamp(e["ts"]) for e in merged)
        cutoff = ref - pd.Timedelta(days=KEEP_DAYS)
        merged = [e for e in merged if pd.Timestamp(e["ts"]) >= cutoff]
        merged.sort(key=lambda e: e["ts"])
    write_events(region, merged)
    write_state(region, _snapshot(data))
    log.info("rotation alerts [%s]: %d new, %d in window (seed=%s)", region, len(new), len(merged), not prior)
    return new
