"""Build the Demand Desk page (site/demand.html) — the market-wide view of the L2
"independent observable" layer (memory demand-desk-divergence).

Per-stock the Demand Context panel answers "is THIS rally's demand already priced?"
This page answers it across the whole covered universe at once: which names show
customer demand / contracted bookings running AHEAD of the priced consensus (the
variant list), which look at-risk, the chain signals driving it, and the scored
ledger's track record + the honest Phase-0 verdict.

Server-side render (mirrors transmission/spr): compute the demand-chain + RPO
reads for every beneficiary, group by divergence, pass to the Jinja template.
Self-contained and resilient — never aborts the build.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from engine import demand_chain as dc
from engine import demand_ledger as dl
from engine.i18n import td, tr
from lib import config
from lib.pages import write_page

log = logging.getLogger("build_demand")

_DIV_ORDER = ["ahead_of_consensus", "consensus_at_risk", "aligned", "signal_only"]
_DIV_META = {
    "ahead_of_consensus": {"cls": "up", "en": "Ahead of consensus", "zh": "领先共识"},
    "consensus_at_risk": {"cls": "risk", "en": "Consensus at risk", "zh": "共识承压"},
    "aligned": {"cls": "mut", "en": "In the price", "zh": "已计入价格"},
    "signal_only": {"cls": "mut", "en": "Signal only", "zh": "仅信号"},
}
_TREND = {"accelerating": ("accelerating", "加速"), "expanding": ("expanding", "扩张"),
          "peaking": ("decelerating", "增速放缓"), "contracting": ("contracting", "收缩"),
          "flat": ("flat", "持平"), "unknown": ("n/a", "不明")}


def _collect(root: Path):
    """All beneficiary reads keyed by ticker (capex chains first, RPO fallback)."""
    sp = root / "data" / "edgar" / "statements.parquet"
    signals = dc.compute_signals(pd.read_parquet(sp)) if sp.exists() else {}
    mem = dl._membership_map(root)
    revs = dl._revisions_map(root)
    baskets = (json.loads((root / "data" / "baskets" / "membership.json").read_text()).get("baskets") or {}) \
        if (root / "data" / "baskets" / "membership.json").exists() else {}
    reads: dict[str, dict] = {}
    for chain in dc.CHAINS:
        if chain["key"] not in signals:
            continue
        cand: set[str] = set()
        for slug in chain["tier_order"]:
            for m in (baskets.get(slug, {}).get("members") or []):
                if not m.get("removed") and m.get("ticker"):
                    cand.add(m["ticker"])
        for tkr in cand:
            r = dc.chain_read(signals, mem.get(tkr), revs.get(tkr), ticker=tkr)
            if r and tkr not in reads:
                reads[tkr] = r
    for tkr, rows in dl._rpo_map(root).items():           # RPO: software complex
        if tkr in reads:
            continue
        r = dc.rpo_read(rows, revs.get(tkr))
        if r:
            reads[tkr] = r
    for tkr, rows in dl._headcount_map(root).items():     # hiring/headcount: last fallback (coincident)
        if tkr in reads:
            continue
        r = dc.hiring_read(rows, revs.get(tkr))
        if r:
            reads[tkr] = r
    return signals, reads


def _chain_cards(signals: dict, reads: dict) -> list[dict]:
    cards = []
    for chain in dc.CHAINS:
        sg = signals.get(chain["key"])
        if not sg:
            continue
        tw = _TREND.get(sg["trend"], _TREND["unknown"])
        cards.append({
            "key": chain["key"], "label_en": chain["label_en"], "label_zh": chain["label_zh"],
            "leading": chain["leading"], "spender_en": chain["spender_en"], "spender_zh": chain["spender_zh"],
            "trend": sg["trend"], "trend_en": tw[0], "trend_zh": tw[1], "yoy_pct": sg["yoy_pct"],
            "total_bn": sg["total_latest_bn"], "fy": sg["fy_latest"], "n": sg["n_spenders"],
            "series": sg["series"],
        })
    # synthetic card for the RPO (own-bookings) cohort
    rpo = [r for r in reads.values() if r["chain_key"] == "own_rpo"]
    if rpo:
        leaders = sorted(rpo, key=lambda r: (r.get("yoy_pct") or -1), reverse=True)[:3]
        cards.append({
            "key": "own_rpo", "label_en": "Software bookings (RPO)", "label_zh": "软件已签约订单（RPO）",
            "leading": True, "spender_en": "Contracted forward bookings", "spender_zh": "已签约前瞻订单",
            "trend": "", "trend_en": "", "trend_zh": "", "yoy_pct": None, "total_bn": None,
            "fy": rpo[0]["fy_latest"], "n": len(rpo), "series": [],
            "leaders": [{"t": _ticker_of(r, reads), "yoy": r.get("yoy_pct"),
                         "bn": r.get("total_latest_bn")} for r in leaders],
        })
    return cards


def _ticker_of(read: dict, reads: dict) -> str:
    for t, r in reads.items():
        if r is read:
            return t
    return "?"


def build(root=None) -> str:
    root = Path(root or config.ROOT)
    signals, reads = _collect(root)
    cards = _chain_cards(signals, reads)

    groups = {k: [] for k in _DIV_ORDER}
    for tkr, r in reads.items():
        tw = _TREND.get(r["trend"], _TREND["unknown"])
        groups[r["divergence"]].append({
            "ticker": tkr, "chain": r["chain_key"], "tier": r["tier"], "leading": r["leading"],
            "trend": r["trend"], "trend_en": tw[0], "trend_zh": tw[1],
            "yoy_pct": r.get("yoy_pct"), "consensus_dir": r["consensus_dir"],
            "headline_en": r["headline"]["en"], "headline_zh": r["headline"]["zh"],
        })
    for k in groups:                                      # strongest signal first
        groups[k].sort(key=lambda x: (x.get("yoy_pct") or -999), reverse=True)

    def _load(name):
        p = root / "data" / "demand_chain" / name
        try:
            return json.loads(p.read_text()) if p.exists() else None
        except Exception:  # noqa: BLE001
            return None

    track, phase0 = _load("track_record.json"), _load("phase0.json")
    n_variants = len(groups["ahead_of_consensus"])
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    as_of = (track or {}).get("as_of") or built[:10]
    # change-detect new/flipped variants into the Alert Center (engine.demand_alerts) —
    # the last discoverability surface. Resilient; seeds silent on the first run.
    try:
        from engine import demand_alerts
        fired = demand_alerts.rebuild(reads, as_of=as_of)
        if fired:
            log.info("build_demand: %d new demand-variant alert(s)", len(fired))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("demand alerts skipped (%s)", e)

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("demand.html.j2").render(
        cards=cards, groups=groups, div_order=_DIV_ORDER, div_meta=_DIV_META,
        track=track, phase0=phase0, n_variants=n_variants, as_of=as_of, built=built)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)
    write_page(site / "demand.html", html)
    log.info("build_demand: %d reads (%d ahead, %d at-risk) → site/demand.html",
             len(reads), n_variants, len(groups["consensus_at_risk"]))
    return html


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        build()
    except Exception as e:  # noqa: BLE001 — resilient leaf page; never abort the deploy
        log.warning("build_demand failed (%s)", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
