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
    "gov_grant":         ("Federal grant/loan", "联邦补助/贷款"),
    "gov_grant_accel":   ("Federal grants accelerating", "联邦补助加速"),
    "lobbying":          ("Lobbying", "游说"),
    "lobbying_spike":    ("Lobbying spike", "游说激增"),
    "fda_approval":      ("FDA approval", "FDA批准"),
    "fda_label_expansion": ("FDA label expansion", "FDA适应症扩展"),
    "material_8k":       ("Material 8-K cluster", "重大8-K集群"),
    "darkpool_accum":    ("Dark-pool accumulation", "暗池吸筹"),
    "13f_add":           ("13F adds", "机构加仓"),
    "smart_money_13f":   ("Smart-money 13F add", "聪明钱13F加仓"),
    "cnbc_pick":         ("CNBC pick", "CNBC推荐"),
    "trump":             ("Donald Trump trade", "特朗普交易"),
    "affiliation":       ("Influence-graph link", "影响力图谱关联"),
    "app_demand":        ("App-store demand", "应用商店需求"),
    "patent_cluster":    ("Patent cluster", "专利集群"),
    "retail_buzz":       ("Retail buzz", "散户热度"),
    "hf_model_momentum": ("AI model adoption", "AI模型采用"),
    "unusual_options":   ("Unusual options flow", "异常期权流"),
    "analyst_upgrade_cluster": ("Analyst upgrades", "分析师上调"),
    "insider_mspr":      ("Insider sentiment", "内部人情绪"),
    "earnings_beat":     ("Earnings beat", "财报超预期"),
    "news_sentiment":    ("Bullish news flow", "看多新闻流"),
    "clinical_phase3_start": ("Phase-3 trial start", "三期试验启动"),
    "github_momentum":   ("Developer adoption", "开发者采用"),
}


# --------------------------------------------------------------------------- co-firing #23
# Channels that fire on the SAME underlying corporate event are ONE observation, not N. The
# audit (#23): of 120 theses, special_situation appears in 73, material_8k 27 — a single 8-K
# can mint a multi-channel "high" tier because convergence_score counts distinct channels as
# independent. We group channels into event CLUSTERS; the co-firing-adjusted score counts
# clusters (independent evidence), not raw channels. This estimate uses the channel taxonomy
# directly (channels within a cluster co-fire on one event); it degrades to the raw count when
# a channel is unmapped (conservative — never over-penalises an unknown channel).
_EVENT_CLUSTER = {
    # a single 8-K / material corporate event lights several of these at once
    "material_8k": "corp_event", "clinical_phase3_start": "corp_event",
    "fda_approval": "corp_event", "fda_label_expansion": "corp_event",
    "earnings_beat": "corp_event", "gov_grant": "corp_event", "gov_grant_accel": "corp_event",
    # one political/trump narrative lights these together
    "trump": "trump", "lobbying": "trump", "lobbying_spike": "trump",
    # congressional disclosure cluster (one filing window)
    "congress_buy": "congress", "congress_cluster": "congress",
    # insider filing cluster (one Form-4 window)
    "insider_buy": "insider", "insider_cluster": "insider", "insider_mspr": "insider",
    # soft social / retail buzz co-move
    "retail_buzz": "buzz", "news_sentiment": "buzz", "cnbc_pick": "buzz",
    # contract flow cluster
    "gov_contract": "contract", "gov_contract_accel": "contract",
}


def cofiring_adjusted_score(chans: list) -> int:
    """Independent-evidence count: channels that co-fire on ONE event collapse to a single
    observation (#23). An unmapped channel keeps its own cluster (conservative). This is the
    number a tier should be built on — a single corporate event can no longer mint a
    multi-channel 'high'."""
    if not chans:
        return 0
    clusters = {_EVENT_CLUSTER.get(str(c), f"solo:{c}") for c in chans}
    return len(clusters)


def convergence_tier(chans: list, trump: bool) -> dict:
    """Accrual-aware, co-firing-penalized tier (#23). Returns::

        {"tier", "raw_score", "cofiring_score", "n_scored", "hit_rate", "basis"}

    ``tier`` is built on the CO-FIRING-ADJUSTED score (independent events), not the raw
    channel count. ``basis`` is 'prior' until the spine's convergence ledger has n>0 matured
    outcomes — then it becomes 'measured' and cites the real hit-rate. The 'weight by track
    record' language is only honest once n_scored>0, so the caller can gate it."""
    raw = len(chans or [])
    cof = cofiring_adjusted_score(chans or [])
    # tier off the ADJUSTED score: 'high' needs >=3 INDEPENDENT events (or 2 + a distinct
    # trump event), so one 8-K lighting 3 channels (cof=1) can no longer be 'high'.
    tier = "high" if (cof >= 3 or (cof >= 2 and trump)) else "medium" if cof >= 2 else "low"
    n_scored, hit_rate, basis = 0, None, "prior"
    try:
        from engine import spine
        m = spine.measured_ic(engine="altdata_conv", family="altdata:convergence")
        n_scored = int(m.get("n") or 0)
        if n_scored > 0:
            hit_rate = m.get("hit_rate")
            basis = "measured"
            # a measured NULL/negative edge demotes 'high'→'medium' (honest override)
            if m.get("wrong_sign") and tier == "high":
                tier = "medium"
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return {"tier": tier, "raw_score": raw, "cofiring_score": cof,
            "n_scored": n_scored, "hit_rate": hit_rate, "basis": basis}


def chip(rec: dict | None) -> dict | None:
    """Shape a by_ticker record into a display-only stock-page chip, or None."""
    if not rec:
        return None
    chans = rec.get("channels") or []
    if not chans:
        return None
    score = int(rec.get("convergence_score", 0) or 0)
    trump = bool(rec.get("trump_linked"))
    # #23: tier off the co-firing-adjusted independent-event count, accrual-aware.
    tinfo = convergence_tier(chans, trump)
    tier = tinfo["tier"]
    cof = tinfo["cofiring_score"]
    labels = [{"en": _CH.get(c, (c, c))[0], "zh": _CH.get(c, (c, c))[1]} for c in chans]
    if cof >= 2:
        # headline the INDEPENDENT-event count (#23), noting when channels collapsed
        collapsed = "" if cof == score else f" (from {score} channels)"
        collapsed_zh = "" if cof == score else f"（{score}通道去相关后）"
        head = {"en": f"{cof}-event alt-data convergence{collapsed}",
                "zh": f"{cof}独立事件替代数据汇聚{collapsed_zh}"}
    elif score >= 1:
        en, zh = _CH.get(chans[0], (chans[0], chans[0]))
        head = {"en": en, "zh": zh}
    else:
        head = {"en": "alt-data signal", "zh": "替代数据信号"}
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
    # #23: the caveat is honest about the ledger's ACTUAL maturity. Only once the spine's
    # convergence ledger has n>0 matured outcomes does "weight by track record" mean anything;
    # until then it is an explicit n=0 PRIOR, not an earned weight.
    n_scored, basis = tinfo["n_scored"], tinfo["basis"]
    if basis == "measured" and n_scored > 0:
        hr = tinfo.get("hit_rate")
        hr_txt = f" (hit-rate {hr:.0%}, n={n_scored})" if hr is not None else f" (n={n_scored})"
        caveat_en = ("Public-record alt-data convergence — the unusual-activity layer. Graded "
                     f"vs SPY in the Signal Intelligence ledger{hr_txt}; weight by that track "
                     "record, not a standalone trade signal.")
        caveat_zh = ("公开记录替代数据汇聚——异常活动层。在信号情报战绩中对标普评分"
                     f"（命中率约，n={n_scored}）；据该战绩权衡，而非独立交易信号。")
    else:
        caveat_en = ("Public-record alt-data convergence — the unusual-activity layer. "
                     "TRACK RECORD ACCRUING (n=0 matured): this tier is a PRIOR, not an earned "
                     "weight; the vs-SPY ledger has not matured. Context only, never a trade signal.")
        caveat_zh = ("公开记录替代数据汇聚——异常活动层。战绩累积中（已到期 n=0）："
                     "此层级为先验，非已验证权重；对标普战绩尚未到期。仅作背景，绝非交易信号。")
    return {
        "tier": tier, "score": score,
        "cofiring_score": cof, "n_scored": n_scored, "basis": basis, "hit_rate": tinfo.get("hit_rate"),
        "trump_linked": trump, "channels": labels,
        "headline": head,
        "detail": {"en": "; ".join(en_bits) or "alt-data signal present",
                   "zh": "；".join(zh_bits) or "存在替代数据信号"},
        "caveat": {"en": caveat_en, "zh": caveat_zh},
    }
