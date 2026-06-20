"""Per-ticker alt-data rollup — the shared substrate the score / narrative / model
layers read.

`engine.altdata` produces CROSS-SECTIONAL signal lists (top congress buys, top
contract winners, …). This module INVERTS them into one record per ticker, so any
downstream consumer (the per-stock conviction chip, theme discovery, the falsifiable
ledger, the Claude-CLI brain) can look a ticker up in O(1):

    data/altdata/by_ticker.json
    { "tickers": { "EFX": {convergence_score, channels, congress_net, gov_contract_usd_30d,
                            insider_net_usd, lobbying_usd, dpi_lean, trump_side, donor_usd}, ... } }

Display / context-only. Pure read of the feed signals; no network, no LLM. The
`convergence_score` = count of DISTINCT independent channels lit on a ticker — the
connection / unusual-activity measure. Corporate-PAC donations are recorded but do
NOT count toward convergence (nearly every large-cap donates, so it would over-fire).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from lib import config
from engine import altdata_models as models

log = logging.getLogger(__name__)


def build(feed: dict, affiliations: dict | None = None) -> dict:
    """Invert feed['signals'] into one weighted record per ticker and persist it.

    Delegates to the single weighted kernel (``altdata_models.channel_records``) so this
    substrate and the cross-sectional ``altdata.convergence`` display never diverge.
    ``convergence_score`` = distinct-channel COUNT (kept for the ledger + downstream
    back-compat); ``weighted_score`` ranks by channel QUALITY. ``affiliations`` (optional,
    {ticker: detail} from the influence graph) adds the 'affiliation' channel so a
    qualitative actor→name edge converges with the hard feeds.
    """
    s = (feed or {}).get("signals", {})
    recs = models.channel_records(s, affiliations=affiliations)
    by: dict[str, dict] = {}
    for tk, r in recs.items():
        chans = r.get("channels", [])
        rec = {k: v for k, v in r.items() if k not in ("channel_detail", "count")}
        rec["convergence_score"] = r.get("count", len(chans))
        rec["trump_linked"] = any(str(c).startswith("trump") for c in chans)
        rec["affiliated"] = "affiliation" in chans
        by[tk] = rec

    now = datetime.now(timezone.utc)
    out = {
        "schema": "altdata.by_ticker.v2",
        "as_of": (feed or {}).get("as_of") or now.date().isoformat(),
        "generated_utc": now.isoformat(),
        "n_tickers": len(by),
        "note": "Per-ticker weighted alt-data rollup. convergence_score = distinct "
                "independent channels (count); weighted_score ranks by channel quality. "
                "Donors / position-size recorded as context, never a voting channel.",
        "tickers": by,
    }
    _write(out)
    log.info("altdata by_ticker: %d tickers, %d with convergence>=2 (max weighted %.2f)",
             len(by), sum(1 for r in by.values() if r["convergence_score"] >= 2),
             max((r["weighted_score"] for r in by.values()), default=0.0))
    return out


def _write(out: dict) -> None:
    for base in (config.data_dir() / "altdata", config.ROOT / "site" / "altdata"):
        base.mkdir(parents=True, exist_ok=True)
        (base / "by_ticker.json").write_text(json.dumps(out, indent=2, default=str))


def load() -> dict:
    p = config.data_dir() / "altdata" / "by_ticker.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------- chip view
# Display-only per-stock chip derived from a by_ticker record (used by the US stock page,
# mirroring stock_macro_sensitivity). Keeps by_ticker.json itself lean.
_CH = {
    "congress_buy":      ("Congress buying", "国会买入"),
    "congress_cluster":  ("Congress cluster-buy", "国会集群买入"),
    "insider_buy":       ("Insider buying", "内部人买入"),
    "insider_cluster":   ("Insider cluster-buy", "内部人集群买入"),
    "gov_contract":      ("Gov contracts", "政府合同"),
    "gov_contract_accel": ("Gov contracts accelerating", "政府合同加速"),
    "lobbying":          ("Lobbying", "游说"),
    "lobbying_spike":    ("Lobbying spike", "游说激增"),
    "darkpool_accum":    ("Dark-pool accumulation", "暗池吸筹"),
    "13f_add":           ("13F adds", "机构加仓"),
    "smart_money_13f":   ("Smart-money 13F add", "聪明钱13F加仓"),
    "cnbc_pick":         ("CNBC pick", "CNBC推荐"),
    "trump":             ("Donald Trump trade", "特朗普交易"),
    "affiliation":       ("Influence-graph link", "影响力图谱关联"),
    "app_demand":        ("App-store demand", "应用商店需求"),
    "patent_cluster":    ("Patent cluster", "专利集群"),
    "retail_buzz":       ("Retail buzz", "散户热度"),
}


def chip(rec: dict | None) -> dict | None:
    """Shape a by_ticker record into a display-only stock-page chip, or None."""
    if not rec:
        return None
    chans = rec.get("channels") or []
    if not chans:
        return None
    score = int(rec.get("convergence_score", 0) or 0)
    trump = bool(rec.get("trump_linked"))
    tier = "high" if (score >= 3 or (score >= 2 and trump)) else "medium" if score >= 2 else "low"
    labels = [{"en": _CH.get(c, (c, c))[0], "zh": _CH.get(c, (c, c))[1]} for c in chans]
    if score >= 2:
        head = {"en": f"{score}-channel alt-data convergence", "zh": f"{score}通道替代数据汇聚"}
    else:
        en, zh = _CH.get(chans[0], (chans[0], chans[0]))
        head = {"en": en, "zh": zh}
    en_bits, zh_bits = [], []
    if rec.get("congress_members"):
        en_bits.append(f"{rec['congress_members']} in Congress net-buying")
        zh_bits.append(f"{rec['congress_members']}位国会议员净买入")
    if rec.get("gov_contract_usd_30d"):
        en_bits.append(f"${rec['gov_contract_usd_30d']:,.0f} gov contracts (30d)")
        zh_bits.append(f"政府合同 ${rec['gov_contract_usd_30d']:,.0f}（30天）")
    if rec.get("insider_net_usd", 0) and rec["insider_net_usd"] > 0:
        en_bits.append(f"${rec['insider_net_usd']:,.0f} net insider buying")
        zh_bits.append(f"内部人净买入 ${rec['insider_net_usd']:,.0f}")
    if rec.get("dpi_lean") == "accumulation":
        en_bits.append("dark-pool accumulation")
        zh_bits.append("暗池吸筹")
    if rec.get("trump_side"):
        en_bits.append(f"Donald Trump {rec['trump_side']}")
        zh_bits.append(f"特朗普{'买入' if rec['trump_side'] == 'buy' else '卖出'}")
    return {
        "tier": tier, "score": score, "trump_linked": trump, "channels": labels,
        "headline": head,
        "detail": {"en": "; ".join(en_bits) or "alt-data signal present",
                   "zh": "；".join(zh_bits) or "存在替代数据信号"},
        "caveat": {"en": "Public-record alt-data convergence — the unusual-activity layer. Graded "
                         "vs SPY in the Signal Intelligence ledger; weight by that track record, "
                         "not a standalone trade signal.",
                   "zh": "公开记录替代数据汇聚——异常活动层。在信号情报战绩中对标普评分；据该战绩权衡，"
                         "而非独立交易信号。"},
    }
