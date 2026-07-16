"""Demand-chain scored ledger — Phase 2 of the Demand Desk (see memory
demand-desk-divergence). Turns the LEADING customer-demand chains' divergence
reads into FALSIFIABLE, forward-scored predictions so we can eventually answer:
does "customer capex ahead of consensus" actually precede relative strength?

This reuses the exact accountability chassis behind engine/ai_desk.py +
engine/policy_intent_desk.py — append-only theses.jsonl with a machine-checkable
rel_return predicate, scored deterministically by engine/ai_desk_scorer.py into
scored.jsonl + track_record.json. Unlike ai_desk the thesis is RULE-DERIVED (the
divergence is deterministic), so there is no LLM call here.

What earns a thesis:
- ONLY leading chains (ai_datacenter; housing is coincident → display-only).
- ONLY divergence ∈ {ahead_of_consensus, consensus_at_risk} — i.e. the chain and
  the priced consensus actually DISAGREE. "aligned" / "signal_only" make no
  falsifiable claim, so they stay display-only (the panel's "stay silent when you
  merely agree with consensus" rule, enforced in the ledger).

Predicate (mirrors ai_desk's overweight/avoid):
- ahead_of_consensus → bet it OUTPERFORMS SPY: miss if rel_return < -5% over the
  chain's horizon, else hit.
- consensus_at_risk → bet it LAGS SPY: miss if rel_return > +5%, else hit.

Honesty: conviction is always "low" — this is an unproven signal being scored
forward to EARN credibility, never a buy signal and never fed into any score.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd

from engine import ai_desk as _desk          # reuse _check_by / _level_asof
from engine import ai_desk_scorer as _scorer  # reuse the predicate evaluators
from engine.regime_label import quad_label    # regime stamp → by_regime track record
from engine import demand_chain as dc
from lib import config

log = logging.getLogger("demand_ledger")


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — the same sentinel set by daily.yml's engine-job
    env.  US_LANE is accepted as a legacy alias.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"

_BENCH = "SPY"
_THRESH = 0.05          # ±5% relative-return falsification band (matches ai_desk)
_ACTIONABLE = ("ahead_of_consensus", "consensus_at_risk")


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _membership_map(root: Path) -> dict[str, list[dict]]:
    """{ticker: [{slug, name}, …]} from data/baskets/membership.json."""
    p = root / "data" / "baskets" / "membership.json"
    if not p.exists():
        return {}
    baskets = (json.loads(p.read_text()).get("baskets") or {})
    out: dict[str, list[dict]] = {}
    for slug, info in baskets.items():
        for m in (info.get("members") or []):
            if m.get("removed") or not m.get("ticker"):
                continue
            out.setdefault(m["ticker"], []).append({"slug": slug, "name": info.get("name")})
    return out


def _revisions_map(root: Path) -> dict[str, dict]:
    p = root / "data" / "revisions" / "latest.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    out: dict[str, dict] = {}
    for t, r in df.iterrows():
        out[str(t)] = {"breadth": _f(r.get("breadth")), "est_chg_30d": _f(r.get("est_chg_30d")),
                       "est_chg_90d": _f(r.get("est_chg_90d"))}
    return out


def _thesis_for(tkr: str, read: dict, asof: str, entry_lvl: float | None,
                spy_lvl: float | None) -> dict | None:
    """Build one falsifiable thesis from a leading-chain divergence read. Pure —
    returns None when the read is not actionable or prices are unavailable."""
    if not read or not read.get("leading"):
        return None
    div = read.get("divergence")
    if div not in _ACTIONABLE:
        return None
    if entry_lvl is None or spy_lvl is None:
        return None
    horizon = int(read.get("horizon_d") or 126)
    bullish = div == "ahead_of_consensus"
    op = "<" if bullish else ">"
    thr = -_THRESH if bullish else _THRESH
    lean = "outperform" if bullish else "underperform"
    vintage = f"{read['chain_key']}:{tkr}:{read['fy_latest']}:{div}"
    if bullish:
        ft_en = (f"FALSE if {tkr} underperforms SPY by >5% over ~{horizon} trading days — i.e. "
                 f"hyperscaler capex running ahead of consensus did NOT translate into relative strength.")
        ft_zh = (f"若 {tkr} 在约 {horizon} 个交易日内跑输 SPY 逾5%，则证伪——"
                 "即领先于共识的云厂商资本开支并未转化为相对强势。")
    else:
        ft_en = (f"FALSE if {tkr} outperforms SPY by >5% over ~{horizon} trading days — i.e. the "
                 f"customer-capex-at-risk read was wrong and it rallied anyway.")
        ft_zh = (f"若 {tkr} 在约 {horizon} 个交易日内跑赢 SPY 逾5%，则证伪——"
                 "即“客户资本开支承压”的判断有误，其反而上涨。")
    return {
        "id": f"{asof}-{read['chain_key']}-{tkr}",
        "logged_at": _scorer._now_iso(),
        "state_asof": asof,
        "chain": read["chain_key"],
        "vintage": vintage,
        "subject": tkr,
        "lean": lean,
        "conviction": "low",
        "horizon_d": horizon,
        "divergence": div,
        "trend": read.get("trend"),
        "yoy_pct": read.get("yoy_pct"),
        "tier": read.get("tier"),
        "falsifier": {
            "text": ft_en, "text_zh": ft_zh,
            "check": {"kind": "rel_return", "subject_ticker": tkr, "vs": _BENCH,
                      "op": op, "threshold": thr, "horizon_d": horizon},
        },
        "check_by": _desk._check_by(asof, horizon),
        "entry_levels": {tkr: entry_lvl, _BENCH: spy_lvl},
        "status": "open", "scored_at": None, "outcome": None, "realized": None,
    }


def _rpo_map(root: Path) -> dict[str, list[dict]]:
    p = root / "data" / "edgar" / "rpo.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    out: dict[str, list[dict]] = {}
    for t, g in df.groupby("ticker"):
        out[str(t)] = [{"fy": int(r.fy), "rpo": float(r.rpo),
                        "revenue": (float(r.revenue) if r.revenue == r.revenue else None)}
                       for r in g.itertuples()]
    return out


def _headcount_map(root: Path) -> dict[str, list[dict]]:
    p = root / "data" / "edgar" / "headcount.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    out: dict[str, list[dict]] = {}
    for t, g in df.groupby("ticker"):
        out[str(t)] = [{"fy": int(r.fy), "employees": int(r.employees)} for r in g.itertuples()]
    return out


def build_theses(root=None, today=None) -> list[dict]:
    """Compute today's actionable theses across all LEADING reads — the customer-
    capex chains AND per-name RPO (contracted forward bookings). Pure of writes."""
    root = Path(root or config.ROOT)
    today = today or date.today()
    asof = today.isoformat()
    mem = _membership_map(root)
    revs = _revisions_map(root)
    spy_lvl = _desk._level_asof(_BENCH, root, asof)
    baskets = (json.loads((root / "data" / "baskets" / "membership.json").read_text()).get("baskets") or {}) \
        if (root / "data" / "baskets" / "membership.json").exists() else {}

    # (ticker, read) candidates from both L2 sources
    candidates: list[tuple[str, dict]] = []
    sp = root / "data" / "edgar" / "statements.parquet"
    signals = dc.compute_signals(pd.read_parquet(sp)) if sp.exists() else {}
    for chain in dc.CHAINS:
        if not chain["leading"] or chain["key"] not in signals:
            continue
        cand: set[str] = set()
        for slug in chain["tier_order"]:
            for m in (baskets.get(slug, {}).get("members") or []):
                if not m.get("removed") and m.get("ticker"):
                    cand.add(m["ticker"])
        for tkr in sorted(cand):
            read = dc.chain_read(signals, mem.get(tkr), revs.get(tkr), ticker=tkr)
            if read:
                candidates.append((tkr, read))
    for tkr, rows in sorted(_rpo_map(root).items()):     # RPO: own contracted bookings (leading)
        read = dc.rpo_read(rows, revs.get(tkr))
        if read:
            candidates.append((tkr, read))

    out, seen = [], set()
    regime = quad_label(root)
    for tkr, read in candidates:
        if not read.get("leading") or read.get("divergence") not in _ACTIONABLE:
            continue
        th = _thesis_for(tkr, read, asof, _desk._level_asof(tkr, root, asof), spy_lvl)
        if th and th["vintage"] not in seen:
            seen.add(th["vintage"])
            th["regime"] = regime
            out.append(th)
    return out


def _read(path: Path) -> dict:
    return _scorer._dedupe_by_id(_scorer._load_jsonl(path))


def emit(root=None, today=None) -> list[dict]:
    """Append new theses (deduped by vintage = chain:ticker:fy:divergence, so a
    name re-emits only when the capex vintage rolls or its divergence flips)."""
    root = Path(root or config.ROOT)
    d = root / "data" / "demand_chain"
    d.mkdir(parents=True, exist_ok=True)
    ledger = _read(d / "theses.jsonl")
    seen_vint = {r.get("vintage") for r in ledger.values()}
    fresh = [t for t in build_theses(root, today) if t["vintage"] not in seen_vint]
    if fresh:
        if _ledger_advance_enabled():
            with open(d / "theses.jsonl", "a", encoding="utf-8") as f:
                for t in fresh:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
        else:
            log.debug(
                "demand_ledger.emit: theses write skipped (COLLECT_LANE != nightly)"
            )
    log.info("demand-ledger: +%d new theses (%d already logged)", len(fresh), len(ledger))
    return fresh


def score(root=None, today=None) -> dict:
    """Score open theses against realized prices (mirrors policy_intent_desk.score)."""
    root = Path(root or config.ROOT)
    today = today or date.today()
    d = root / "data" / "demand_chain"
    led = _read(d / "theses.jsonl")
    scored = _read(d / "scored.jsonl")
    new = []
    for tid, row in led.items():
        if tid in scored:
            continue
        s = _scorer._score_one(row, root, today)
        if s:
            new.append(s)
    if new:
        if _ledger_advance_enabled():
            with open(d / "scored.jsonl", "a", encoding="utf-8") as f:
                for s in new:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")
        else:
            log.debug(
                "demand_ledger.score: scored.jsonl write skipped "
                "(COLLECT_LANE != nightly)"
            )
    tr = _scorer._aggregate(list(scored.values()) + new, led, today)
    tr["schema"] = "demand_chain_track_record.v1"
    if _ledger_advance_enabled():
        (d / "track_record.json").write_text(json.dumps(tr, indent=2, ensure_ascii=False))
    else:
        log.debug(
            "demand_ledger.score: track_record.json write skipped "
            "(COLLECT_LANE != nightly)"
        )
    log.info("demand-ledger: scored=%d open=%d (+%d newly scored)",
             tr.get("scored_total", 0), tr.get("open", 0), len(new))
    return tr


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    emit()          # append today's fresh theses
    score()         # then score everything due
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
