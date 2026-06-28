"""Subsector-rotation alert engine — fires when a subsector ROTATES.

A sibling of engine.theme_alerts / engine.emergence_alerts. The rotation read
(engine.subsector_rotation) is a per-run model output with no stored series, so
this is CHANGE-DETECTION across runs: it diffs each subsector's rotation *state*
(is it in the accelerating "emerging" set; is it a leader that just rolled over)
against the prior snapshot in data/subsector_rotation/state.json and emits one
event when a subsector crosses a boundary —

  rotation_emerging   a subsector newly enters the Improving/Leading quadrant
                      with positive acceleration (a rotate-IN early signal).
  rotation_fading     a former leader newly flips to Weakening (rotate-OUT).

Event schema matches the other engines (id, ts, source='rotation', asset, type,
severity, headline/detail + _zh, context, anchor) so engine.alert_triage picks
it up with zero new plumbing. FIRST run (no prior state) SEEDS silently — never
an alert storm. CONTEXT-ONLY: a rotation read carries no validated forward edge;
it rides Finviz's broad-universe numbers (names we hold no prices for).
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
EMERGE_MIN = 1.0          # emerging_score bar — only meaningful accelerating flips
REGION = "us"


def _dir():
    return config.data_dir() / "subsector_rotation"


def _state_path():
    return _dir() / "state.json"


def _path():
    return _dir() / "alerts.jsonl"


def load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def write_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def _is_emerging(s: dict) -> bool:
    return (s.get("quadrant") in ("improving", "leading")
            and (s.get("rs_mom") or 0) > 0
            and (s.get("accel") is None or (s.get("accel") or 0) > 0)
            and (s.get("emerging_score") or 0) >= EMERGE_MIN)


def _snapshot(payload: dict) -> dict:
    """Per-subsector fields we diff against next run."""
    return {s["key"]: {"name": s["name"], "theme": s.get("theme", ""),
                       "quadrant": s.get("quadrant"), "emerging": _is_emerging(s)}
            for s in payload.get("subsectors", []) if s.get("key")}


def _ev(key, ts, type_, severity, headline, detail, context, headline_zh="", detail_zh=""):
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"rotation:{REGION}:{type_}:{key}:{bucket}", "ts": ts.isoformat(),
            "source": "rotation", "asset": key, "type": type_,
            "severity": severity, "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": "#rotation-app"}


def compute_events(payload: dict, prior: dict | None) -> list[dict]:
    """One event per subsector that crossed a rotation boundary this run.

    Seeds silent on the first run (no prior state)."""
    prior = prior or {}
    if not prior:                       # first run → seed, never storm
        return []
    ts = payload.get("generated_utc") or payload.get("asof") or pd.Timestamp.utcnow().isoformat()
    out = []
    cur = {s["key"]: s for s in payload.get("subsectors", []) if s.get("key")}
    for key, s in cur.items():
        was = prior.get(key) or {}
        emerging_now = _is_emerging(s)
        nm, th = s["name"], s.get("theme", "")
        qd = s.get("quadrant")
        # rotate-IN: newly emerging (was not in the accelerating set).
        if emerging_now and not was.get("emerging"):
            sev = "high" if (s.get("emerging_score") or 0) >= 1.8 else "minor"
            qword = "leading" if qd == "leading" else "improving"
            hl = f"🌀 Rotating in — {nm} ({th})"
            hl_zh = f"🌀 资金轮入 — {nm}（{th}）"
            det = (f"{nm} just turned {qword} & accelerating "
                   f"(1W {_pc(s,'1W')}, 1M {_pc(s,'1M')}, 3M {_pc(s,'3M')}; accel {_f(s.get('accel'))}). "
                   f"An early rotate-in candidate — context, not a buy list.")
            det_zh = (f"{nm} 刚转为{('领先' if qd=='leading' else '改善')}且加速"
                      f"（1周 {_pc(s,'1W')}，1月 {_pc(s,'1M')}，3月 {_pc(s,'3M')}；加速 {_f(s.get('accel'))}）。"
                      f"早期轮入候选 — 仅作参考，非买入清单。")
            out.append(_ev(key, ts, "rotation_emerging", sev, hl, det,
                           {"quadrant": qd, "accel": s.get("accel"),
                            "emerging_score": s.get("emerging_score")}, hl_zh, det_zh))
        # rotate-OUT: a prior leader/improver newly flips to weakening.
        elif qd == "weakening" and was.get("quadrant") in ("leading", "improving") \
                and (s.get("rs_ratio") or 0) > 0:
            hl = f"🌀 Rolling over — {nm} ({th})"
            hl_zh = f"🌀 龙头走弱 — {nm}（{th}）"
            det = (f"{nm} was leading but momentum has rolled over to weakening "
                   f"(1W {_pc(s,'1W')}, 3M {_pc(s,'3M')}; mom {_f(s.get('rs_mom'))}). "
                   f"A rotate-out / take-profit watch — context only.")
            det_zh = (f"{nm} 此前领先，但动量已转弱"
                      f"（1周 {_pc(s,'1W')}，3月 {_pc(s,'3M')}；动量 {_f(s.get('rs_mom'))}）。"
                      f"轮出/止盈观察 — 仅作参考。")
            out.append(_ev(key, ts, "rotation_fading", "minor", hl, det,
                           {"quadrant": qd, "rs_mom": s.get("rs_mom")}, hl_zh, det_zh))
    return out


def _pc(s, h):
    v = (s.get("perf") or {}).get(h)
    return "—" if v is None else (("+" if v > 0 else "") + f"{v:.1f}%")


def _f(v):
    return "—" if v is None else (("+" if v > 0 else "") + f"{v:.1f}")


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


def write_events(events: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def recent(days: int = 30, as_of: str | None = None) -> list[dict]:
    evs = load_events()
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def rebuild(payload: dict) -> list[dict]:
    """Diff vs prior state, append+dedup new events into the jsonl, persist state.
    Returns the events fired THIS run (empty on the seed run)."""
    if not payload or not payload.get("subsectors"):
        return []
    prior = load_state()
    new_events = compute_events(payload, prior)

    by_id = {e["id"]: e for e in load_events()}
    for e in new_events:
        by_id.setdefault(e["id"], e)
    merged = list(by_id.values())
    if merged:
        ref = max(pd.Timestamp(e["ts"]) for e in merged)
        cutoff = ref - pd.Timedelta(days=KEEP_DAYS)
        merged = [e for e in merged if pd.Timestamp(e["ts"]) >= cutoff]
        merged.sort(key=lambda e: e["ts"])
    write_events(merged)
    write_state(_snapshot(payload))
    return new_events
