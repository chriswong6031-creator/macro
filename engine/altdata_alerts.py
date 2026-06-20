"""Alternative-data alert engine — fires when a ticker becomes multi-channel
convergent, run over run.

Mirrors engine.theme_alerts: CHANGE-DETECTION across runs (a convergence is a
recomputed daily state, so we only fire when a ticker ENTERS convergence or its
score INCREASES — never every day it merely persists). The event schema matches the
other engines (id, ts, source='altdata', asset, type, severity, headline/detail +
_zh, context, anchor) so engine.alert_triage picks it up once 'altdata' is
registered there. Writes data/altdata/alerts.jsonl (append + dedup by id, ~90d) and
data/altdata/alerts_state.json (last-seen score per ticker). FIRST run seeds
silently.

DISPLAY / CONTEXT ONLY — a convergence is an unusual-activity flag, not a validated
edge, so the loudest it gets in triage is 'watch'.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
MIN_SCORE = 2  # a ticker must be lit by >=2 distinct channels to alert


def _dir():
    return config.data_dir() / "altdata"


def _path():
    return _dir() / "alerts.jsonl"


def _state_path():
    return _dir() / "alerts_state.json"


def _ev(asset, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"altdata:{asset}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "altdata", "asset": asset, "type": type_, "severity": severity,
            "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": "#convergence"}


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


def load_events(region: str = "us") -> list[dict]:
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


def recent(days: int = 30, as_of: str | None = None, region: str = "us") -> list[dict]:
    evs = load_events()
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def compute_events(by_ticker: dict, prior: dict) -> list[dict]:
    ts = by_ticker.get("as_of") or datetime.now(timezone.utc).date().isoformat()
    events: list[dict] = []
    for tk, rec in (by_ticker.get("tickers") or {}).items():
        score = int(rec.get("convergence_score", 0) or 0)
        if score < MIN_SCORE:
            continue
        if score <= int(prior.get(tk, 0) or 0):
            continue  # only on ENTER or INCREASE — not while it persists
        chans = rec.get("channels", [])
        trump = bool(rec.get("trump_linked"))
        sev = "high" if (score >= 3 or trump) else "medium"
        ch_str = ", ".join(chans)
        head = f"🔗 {score}-channel convergence on {tk}"
        det = f"{tk} lit up by {score} independent alt-data channels: {ch_str}."
        det_zh = f"{tk} 被 {score} 个独立替代数据渠道同时触发：{ch_str}。"
        if trump:
            head += " (Trump-linked)"
            det += " Includes a Donald Trump trade."
            det_zh += "（含特朗普交易）"
        events.append(_ev(tk, "convergence", ts, sev, head, det,
                          {"score": score, "channels": chans, "trump_linked": trump},
                          f"s{score}", f"🔗 {tk} {score}通道汇聚" + ("（特朗普关联）" if trump else ""),
                          det_zh))
    return events


def rebuild(by_ticker: dict) -> list[dict]:
    """Diff vs prior scores, append+dedup new events, persist new state."""
    if not by_ticker or not by_ticker.get("tickers"):
        return []
    prior = load_state()
    new_events = compute_events(by_ticker, prior)

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
    write_state({tk: int(r.get("convergence_score", 0) or 0)
                 for tk, r in by_ticker["tickers"].items()
                 if int(r.get("convergence_score", 0) or 0) >= MIN_SCORE})
    log.info("altdata alerts: %d new, %d in window (seed=%s)",
             len(new_events), len(merged), not prior)
    return new_events
