"""Theme Rotation alert engine — fires when a theme's READ changes, run over run.

Unlike the price-driven alert engines (bonds/forex/commodity recompute a full event
history from a time series), a theme's LABEL and RECOMMENDATION are model outputs with
no stored historical series, so this engine is CHANGE-DETECTION across runs: it diffs
today's engine.theme_scoring payload against the prior snapshot persisted in
data/themes/state.json and emits an event only when something actually flipped —

  reco_change          a basket's recommendation moved (e.g. HOLD -> ACCUMULATE)
  theme_emerging       a basket entered the EMERGING lifecycle
  theme_topping        a DOMINANT leader rolled over into FADING
  theme_deteriorating  a basket broke down into DETERIORATING
  leadership_rotation  a new theme took the #1 score rank

Event schema matches the other engines (id, ts, source='themes', asset, type, severity,
headline/detail + _zh, context, anchor) so engine.alert_triage picks it up with zero new
plumbing. Writes data/themes/alerts.jsonl (append + dedup by id, ~90d kept) and the
state snapshot. FIRST run (no prior state) SEEDS silently — never an alert storm.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
# raw severity per (type, direction) — `high` becomes a 'major' band on the watch tier
# in alert_triage; everything else reads minor. Reserve `high` for the calls that matter.
_RECO_RANK = {"avoid": 0, "trim": 1, "hold": 2, "accumulate": 3, "enter": 4}


def _ev(asset, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"themes:{asset}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "themes", "asset": asset, "type": type_, "severity": severity,
            "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": f"#theme-{asset}"}


def _dir(region: str = "us"):
    # US keeps the original data/themes/ path; other markets get data/themes_<region>/
    return config.data_dir() / ("themes" if region == "us" else f"themes_{region}")


def _state_path(region: str = "us"):
    return _dir(region) / "state.json"


def _path(region: str = "us"):
    return _dir(region) / "alerts.jsonl"


def load_state(region: str = "us") -> dict:
    p = _state_path(region)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def write_state(state: dict, region: str = "us") -> None:
    p = _state_path(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def _snapshot(theme_intel: dict) -> dict:
    """The per-theme fields we diff against next run."""
    return {t["id"]: {"label": t["label"], "reco": t["reco"], "rank": t["rank"],
                      "name": t["name"], "name_zh": t["name_zh"], "score": t["score"]}
            for t in theme_intel.get("themes", [])}


def compute_events(theme_intel: dict, prior: dict | None) -> list[dict]:
    """Diff today's read vs the prior snapshot. prior empty/None -> seed run, no events."""
    if not prior:
        return []
    ts = theme_intel.get("as_of")
    cur = _snapshot(theme_intel)
    events: list[dict] = []
    labelled: set[str] = set()      # baskets that already got a label event (skip their reco dup)

    for tid, c in cur.items():
        p = prior.get(tid)
        if not p:
            continue
        nm, nz = c["name"], c["name_zh"]

        # --- label transitions (the headline narrative changes) ---
        if c["label"] == "emerging" and p.get("label") != "emerging":
            labelled.add(tid)
            events.append(_ev(tid, "theme_emerging", ts, "medium",
                              f"🌱 {nm} is emerging",
                              f"{nm} entered the EMERGING lifecycle — accelerating relative strength "
                              f"before it is extended (score {c['score']}).",
                              {"from": p.get("label"), "to": "emerging", "score": c["score"]}, "emerging",
                              f"🌱 {nz} 进入新兴阶段",
                              f"{nz} 进入「新兴」阶段 — 相对强度加速且尚未过度延展（评分 {c['score']}）。"))
        elif c["label"] == "fading" and p.get("label") == "dominant":
            labelled.add(tid)
            events.append(_ev(tid, "theme_topping", ts, "high",
                              f"⚠️ {nm} is topping out",
                              f"{nm} rolled over from DOMINANT into FADING — strength fading off a high. "
                              f"Recommendation now {c['reco'].upper()}.",
                              {"from": "dominant", "to": "fading", "reco": c["reco"]}, "fading",
                              f"⚠️ {nz} 见顶回落",
                              f"{nz} 自「主导」转入「退潮」 — 高位强度减弱，当前建议 {c['reco'].upper()}。"))
        elif c["label"] == "deteriorating" and p.get("label") != "deteriorating":
            labelled.add(tid)
            events.append(_ev(tid, "theme_deteriorating", ts, "high",
                              f"🔻 {nm} is deteriorating",
                              f"{nm} broke down into DETERIORATING — momentum and breadth weakening "
                              f"together. Recommendation now {c['reco'].upper()}.",
                              {"from": p.get("label"), "to": "deteriorating", "reco": c["reco"]}, "deteriorating",
                              f"🔻 {nz} 走弱",
                              f"{nz} 转入「走弱」 — 动量与广度同步转弱，当前建议 {c['reco'].upper()}。"))

        # --- recommendation flip (skip if a label event already narrates this basket) ---
        if c["reco"] != p.get("reco") and tid not in labelled:
            up = _RECO_RANK.get(c["reco"], 2) > _RECO_RANK.get(p.get("reco"), 2)
            into_strong = c["reco"] in ("enter", "avoid")
            sev = "high" if into_strong else "medium"
            arrow = "↑" if up else "↓"
            events.append(_ev(tid, "reco_change", ts, sev,
                              f"{arrow} {nm}: {p.get('reco','?').upper()} → {c['reco'].upper()}",
                              f"Theme recommendation for {nm} changed from {p.get('reco','?').upper()} "
                              f"to {c['reco'].upper()} (score {c['score']}, {c['label']}).",
                              {"from": p.get("reco"), "to": c["reco"], "score": c["score"]},
                              c["reco"],
                              f"{arrow} {nz}：{p.get('reco','?').upper()} → {c['reco'].upper()}",
                              f"{nz} 的主题建议由 {p.get('reco','?').upper()} 变为 {c['reco'].upper()}"
                              f"（评分 {c['score']}，{c['label']}）。"))

    # --- leadership rotation: a new #1 score rank ---
    new_lead = next((t for t in cur.values() if t["rank"] == 1), None)
    old_lead_id = next((tid for tid, p in prior.items() if p.get("rank") == 1), None)
    if new_lead and old_lead_id and old_lead_id not in (
            tid for tid, t in cur.items() if t["rank"] == 1):
        lead_id = next(tid for tid, t in cur.items() if t["rank"] == 1)
        events.append(_ev(lead_id, "leadership_rotation", ts, "medium",
                          f"🔄 New theme leader: {new_lead['name']}",
                          f"{new_lead['name']} took the #1 theme rank (score {new_lead['score']}), "
                          f"displacing {prior.get(old_lead_id, {}).get('name', old_lead_id)}.",
                          {"new_leader": lead_id, "old_leader": old_lead_id}, "lead",
                          f"🔄 新主题领涨：{new_lead['name_zh']}",
                          f"{new_lead['name_zh']} 升至主题排名第一（评分 {new_lead['score']}），"
                          f"取代 {prior.get(old_lead_id, {}).get('name_zh', old_lead_id)}。"))
    return events


def load_events(region: str = "us") -> list[dict]:
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


def write_events(events: list[dict], region: str = "us") -> None:
    p = _path(region)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def recent(days: int = 30, as_of: str | None = None, region: str = "us") -> list[dict]:
    """Events within the trailing window, newest first (for the page bell dropdown)."""
    evs = load_events(region)
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def rebuild(theme_intel: dict, region: str = "us") -> list[dict]:
    """Diff vs prior state, append+dedup new events into the jsonl, persist new state.
    Returns the events fired THIS run (empty on the seed run)."""
    if not theme_intel or not theme_intel.get("themes"):
        return []
    prior = load_state(region)
    new_events = compute_events(theme_intel, prior)

    # merge into history: keep-first by id, then trim to the KEEP_DAYS window
    by_id = {e["id"]: e for e in load_events(region)}
    for e in new_events:
        by_id.setdefault(e["id"], e)
    merged = list(by_id.values())
    if merged:
        ref = max(pd.Timestamp(e["ts"]) for e in merged)
        cutoff = ref - pd.Timedelta(days=KEEP_DAYS)
        merged = [e for e in merged if pd.Timestamp(e["ts"]) >= cutoff]
        merged.sort(key=lambda e: e["ts"])
    write_events(merged, region)
    write_state(_snapshot(theme_intel), region)
    log.info("theme alerts [%s]: %d new event(s), %d in window (seed=%s)",
             region, len(new_events), len(merged), not prior)
    return new_events
