"""Subsector-rotation alert engine — fires when a subsector ROTATES.

A sibling of engine.theme_alerts / engine.emergence_alerts. The rotation read
(engine.subsector_rotation) is a per-run model output with no stored series, so
this is CHANGE-DETECTION across runs: it diffs each subsector's rotation *state*
(is it in the accelerating "emerging" set; is it a leader that just rolled over)
against the prior snapshot in data/subsector_rotation/state.json and emits one
event when a subsector crosses a boundary —

  rotation_turn_up    a subsector's CYCLE turn up is confirmed across sessions — it fell,
                      then turned, and held (engine.subsector_turn). Severity carries a
                      size + breadth term, so a one-name move cannot print `high`.
  rotation_turn_down  the mirror: it ran, then rolled over, confirmed.
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
                       "quadrant": s.get("quadrant"), "emerging": _is_emerging(s),
                       "turn_state": s.get("turn_state")}
            for s in payload.get("subsectors", []) if s.get("key")}


def _turn_severity(s: dict, up: bool) -> str:
    """Severity from SIZE and BREADTH, not from how excited the copy is.

    RC-R5 (Rotation Command §3) recorded the failure this addresses: the desk fired 21
    alerts a run, all at `minor`, so the one that mattered was indistinguishable from the
    other twenty. A confirmed turn earns `high` only when the node is broad enough to be a
    rotation and its members actually participated — a single-name move stays `minor`
    however violent its z-score.
    """
    confirmed = s.get("turn_state") in ("turn_up", "turn_down")
    n = int(s.get("n_members") or 0)
    brd = (s.get("breadth") or {}).get("turn_up" if up else "turn_dn")
    score = float(s.get("bottom_score" if up else "top_score") or 0.0)
    if confirmed and n >= 6 and (brd or 0) >= 0.7 and score >= 0.70:
        return "high"
    if confirmed and n >= 4:
        return "medium"
    return "minor"


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
        # ── TURN events (engine/subsector_turn.py): a confirmed cycle turn, fired once on
        # the transition into the confirmed state. These lead the triage; the quadrant-flow
        # events below stay as they were.
        # Seed the turn lane silently when the prior snapshot has no `turn_state` at all —
        # a state file written before the turn engine shipped, or a node's first ever
        # appearance. Without this, the first run after deploy fires every already-confirmed
        # turn at once (11 on the 2026-07-30 cross-section), which is the alert storm the
        # seed-silent rule exists to prevent, not a set of transitions that happened today.
        st_now, st_was = s.get("turn_state"), was.get("turn_state")
        if "turn_state" not in was:
            st_now = None
        if st_now in ("turn_up", "turn_down") and st_now != st_was:
            up = st_now == "turn_up"
            sev = _turn_severity(s, up)
            brd = (s.get("breadth") or {}).get("turn_up" if up else "turn_dn")
            brd_txt = f"{round((brd or 0) * 100)}% of members" if brd is not None else "breadth n/a"
            brd_zh = f"{round((brd or 0) * 100)}% 成分股" if brd is not None else "成分股数据不足"
            conc = " · carried by one name" if (s.get("breadth") or {}).get("concentrated") else ""
            conc_zh = " · 主要由单一成分股带动" if (s.get("breadth") or {}).get("concentrated") else ""
            if up:
                hl = f"🔄 Turned up — {nm} ({th})"
                hl_zh = f"🔄 转为上行 — {nm}（{th}）"
                det = (f"{nm} fell {_f(s.get('dd_from_peak'))}% from its 1-year high and has now "
                       f"turned up on confirmed sessions — this week {_pc(s, '1W')} vs the market's "
                       f"{_f((s.get('pace_mkt') or {}).get('w1'))}%/wk, {brd_txt} turning with it{conc}. "
                       f"Context, not a buy list.")
                det_zh = (f"{nm} 自一年高点回落 {_f(s.get('dd_from_peak'))}%，现已连续多个交易日确认转为上行"
                          f"——本周 {_pc(s, '1W')}，市场为 {_f((s.get('pace_mkt') or {}).get('w1'))}%/周，"
                          f"{brd_zh}同步转向{conc_zh}。仅作参考，非买入清单。")
            else:
                hl = f"🔄 Turned down — {nm} ({th})"
                hl_zh = f"🔄 转为下行 — {nm}（{th}）"
                det = (f"{nm} ran {_f(s.get('up_from_trough'))}% off its 1-year low and has now "
                       f"rolled over on confirmed sessions — this week {_pc(s, '1W')} vs the market's "
                       f"{_f((s.get('pace_mkt') or {}).get('w1'))}%/wk, {brd_txt} rolling with it{conc}. "
                       f"Context, not a sell list.")
                det_zh = (f"{nm} 自一年低点上涨 {_f(s.get('up_from_trough'))}%，现已连续多个交易日确认转为下行"
                          f"——本周 {_pc(s, '1W')}，市场为 {_f((s.get('pace_mkt') or {}).get('w1'))}%/周，"
                          f"{brd_zh}同步走弱{conc_zh}。仅作参考，非卖出清单。")
            out.append(_ev(key, ts, f"rotation_{st_now}", sev, hl, det,
                           {"turn_state": st_now, "since": s.get("turn_since"),
                            "score": s.get("turn_score"), "n_members": s.get("n_members"),
                            "breadth": brd, "legs": s.get("legs_up" if up else "legs_dn"),
                            "dd_from_peak": s.get("dd_from_peak"),
                            "up_from_trough": s.get("up_from_trough")}, hl_zh, det_zh))
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
