"""Forming-narrative alert engine — fires when our models detect a NEW narrative forming.

A sibling of engine.theme_alerts. The emergence read (engine.narrative_emergence) is a
model output with no stored historical series, so this is CHANGE-DETECTION across runs: it
diffs today's set of forming-narrative SIGNATURES (a stable hash of each cluster's
constituent set) against the prior snapshot in data/emergence/state_<region>.json and emits
one event when a genuinely new narrative crosses the "meaningfully forming" score bar —

  narrative_forming   a coherent, tightening group of names (not in any basket) newly
                      surfaced by the radar at score >= ALERT_MIN.

Event schema matches the other engines (id, ts, source='emergence', asset, type, severity,
headline/detail + _zh, context, anchor='#ne-<sig>') so engine.alert_triage picks it up with
zero new plumbing. Writes data/emergence/alerts_<region>.jsonl (append + dedup by id,
~90d kept) and the state snapshot. FIRST run (no prior state) SEEDS silently — never an
alert storm. CONTEXT-ONLY: a forming narrative carries no validated forward edge.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
ALERT_MIN = 55.0          # only alert on "Forming" / "Forming fast", not faint early noise


def _dir(region: str = "us"):
    return config.data_dir() / ("emergence" if region == "us" else f"emergence_{region}")


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


def _snapshot(emergence: dict) -> dict:
    """The per-signature fields we diff against next run."""
    return {nv["signature"]: {"name_en": nv["name_en"], "name_zh": nv["name_zh"],
                              "score": nv["score"]}
            for nv in emergence.get("narratives", []) if nv.get("signature")}


def _ev(region, sig, ts, severity, headline, detail, context, headline_zh="", detail_zh=""):
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"emergence:{region}:{sig}:{bucket}", "ts": ts.isoformat(),
            "source": "emergence", "asset": sig, "type": "narrative_forming",
            "severity": severity, "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": f"#ne-{sig}"}


def compute_events(emergence: dict, prior: dict | None) -> list[dict]:
    """One event per NEWLY-seen forming narrative at score >= ALERT_MIN. Seeds silent."""
    prior = prior or {}
    if not prior:                       # first run → seed, never storm
        return []
    region = emergence.get("region", "us")
    ts = emergence.get("as_of") or emergence.get("generated_at")
    out = []
    for nv in emergence.get("narratives", []):
        sig = nv.get("signature")
        if not sig or sig in prior or nv.get("score", 0) < ALERT_MIN:
            continue
        recs = ", ".join(r["ticker"] for r in (nv.get("recommended") or [])[:4])
        sev = "high" if nv.get("score", 0) >= 65 else "minor"
        hl = f"🔥 New forming narrative — {nv['name_en']}"
        hl_zh = f"🔥 新成形叙事 — {nv['name_zh']}"
        det = (f"Score {nv['score']} ({nv['score_label']['en']}); {nv['n']} names tightening. "
               f"Watch: {recs}. Candidate for review — not a buy list.")
        det_zh = (f"评分 {nv['score']}（{nv['score_label']['zh']}）；{nv['n']} 只个股共动收紧。"
                  f"关注：{recs}。供审阅的候选 — 非买入清单。")
        out.append(_ev(region, sig, ts, sev, hl, det,
                       {"score": nv["score"], "n": nv["n"], "recommended": recs},
                       hl_zh, det_zh))
    return out


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


def rebuild(emergence: dict, region: str = "us") -> list[dict]:
    """Diff vs prior state, append+dedup new events into the jsonl, persist new state.
    Returns the events fired THIS run (empty on the seed run)."""
    if not emergence or not emergence.get("narratives"):
        return []
    region = emergence.get("region", region)
    prior = load_state(region)
    new_events = compute_events(emergence, prior)

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
    write_state(_snapshot(emergence), region)
    return new_events
