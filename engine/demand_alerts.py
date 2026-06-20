"""Demand-variant alert engine — fires when a name NEWLY shows an independent
forward-demand signal diverging from the priced consensus (Demand Desk L2; see
memory demand-desk-divergence). The last discoverability surface: push the variant
to the Alert Center instead of waiting for the user to check the board / page.

A sibling of engine.emergence_alerts. The demand reads (engine.demand_chain) carry
no stored historical series, so this is CHANGE-DETECTION across runs: it diffs
today's set of ACTIONABLE divergences ({ticker: divergence} for ahead_of_consensus
/ consensus_at_risk) against data/demand_chain/alerts_state.json and emits one event
per name that is newly actionable or has flipped direction —

  demand_ahead    independent demand (customer capex / contracted bookings / hiring)
                  newly running AHEAD of this name's analyst consensus.
  demand_at_risk  the independent signal newly SOFTENING while estimates still rise.

Event schema matches the other engines so engine.alert_triage picks it up with zero
new plumbing. CONTEXT tier only — the layer is explicitly display-only / not a buy
signal (the forward ledger hasn't earned a verdict). FIRST run (no prior state)
SEEDS silently. Writes data/demand_chain/alerts.jsonl (append + dedup, ~90d kept).
"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

KEEP_DAYS = 90
_ACTIONABLE = ("ahead_of_consensus", "consensus_at_risk")


def _dir():
    return config.data_dir() / "demand_chain"


def _state_path():
    return _dir() / "alerts_state.json"


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


def _actionable(reads: dict) -> dict:
    """{ticker: divergence} for the actionable reads only."""
    return {t: r["divergence"] for t, r in (reads or {}).items()
            if isinstance(r, dict) and r.get("divergence") in _ACTIONABLE}


def _ev(tkr, read, ts):
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    div = read["divergence"]
    ahead = div == "ahead_of_consensus"
    chain = read.get("chain_key", "")
    yoy = read.get("yoy_pct")
    yoy_s = (f" ({'+' if yoy >= 0 else ''}{yoy:.0f}% YoY)") if yoy is not None else ""
    if ahead:
        hl = f"🧭 Demand variant — {tkr}: independent demand ahead of consensus"
        hl_zh = f"🧭 需求变体 — {tkr}：独立需求领先于共识"
        det = (f"{chain}{yoy_s} is running ahead of {tkr}'s analyst revisions — a forward-demand "
               "signal not yet fully in the price. Context for review; not a buy signal.")
        det_zh = (f"{chain}{yoy_s} 跑在 {tkr} 分析师评级调整之前——一个尚未充分计入价格的前瞻需求信号。"
                  "供审阅参考；非买入信号。")
    else:
        hl = f"🧭 Demand caution — {tkr}: independent demand softening vs rising estimates"
        hl_zh = f"🧭 需求警示 — {tkr}：独立需求走弱而预期仍在上修"
        det = (f"{chain}{yoy_s} is softening while {tkr}'s estimates still rise — the priced consensus "
               "may be ahead of the demand. Context; not a sell signal.")
        det_zh = (f"{chain}{yoy_s} 在走弱，而 {tkr} 的预期仍在上修——已被定价的共识可能领先于需求。"
                  "供参考；非卖出信号。")
    return {"id": f"demand:{tkr}:{div}:{bucket}", "ts": ts.isoformat(),
            "source": "demand", "asset": tkr, "type": "demand_ahead" if ahead else "demand_at_risk",
            "severity": "minor", "tier": "context",
            "headline": hl, "detail": det, "headline_zh": hl_zh, "detail_zh": det_zh,
            "context": {"chain": chain, "divergence": div, "yoy": yoy}, "anchor": ""}


def compute_events(reads: dict, prior: dict | None, as_of: str) -> list[dict]:
    """One event per name newly actionable or flipped direction. Seeds silent."""
    prior = prior or {}
    if not prior:                       # first run → seed, never storm
        return []
    out = []
    cur = _actionable(reads)
    for tkr, div in cur.items():
        if prior.get(tkr) == div:        # unchanged → no re-fire
            continue
        out.append(_ev(tkr, reads[tkr], as_of))
    return out


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
    with open(p, "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def recent(days: int = 30, as_of: str | None = None) -> list[dict]:
    evs = load_events()
    if not evs:
        return []
    ref = pd.Timestamp(as_of) if as_of else max(pd.Timestamp(e["ts"]) for e in evs)
    cutoff = ref - pd.Timedelta(days=days)
    out = [e for e in evs if pd.Timestamp(e["ts"]) >= cutoff]
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def rebuild(reads: dict, as_of: str | None = None) -> list[dict]:
    """Diff today's actionable reads vs prior state, append+dedup new events into the
    jsonl, persist the new state. Returns events fired THIS run (empty on seed run)."""
    if not reads:
        return []
    as_of = as_of or date.today().isoformat()
    prior = load_state()
    new_events = compute_events(reads, prior, as_of)

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
    write_state(_actionable(reads))
    return new_events
