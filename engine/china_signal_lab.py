"""China Signal Lab — the honest validation scorecard for every China signal.

LEAF · DISPLAY-ONLY. The China sibling of engine/signal_lab.py: a curated, transparent
registry that states, for each China signal, its TIER (scored / confirmer / display /
pending / killed) and an honest one-line verdict — so the Alt-Data desk never overclaims.
The three SCORED legs are the ones already wired into china_masterminds' regime de-risk
layer; everything alt-data is display or a Phase-0 candidate. No computation, no edge claim.
See research/CHINA_INTEL_POWERHOUSE.md §2.
"""
from __future__ import annotations

from datetime import datetime, timezone

SCHEMA = "china_signal_lab.v2"

TIERS = ("scored", "confirmer", "display", "pending", "killed")

# Per-consumer DEFAULT priors (used until china_validation earns weights). Keys = leg names the
# consumer's combine() expects.
_PRIORS = {
    "altdata": {"value": 0.24, "margin": 0.20, "flow": 0.18, "comment": 0.15, "lhb": 0.10,
                "block": 0.05, "analyst": 0.08},
    "conviction": {"radar": 0.40, "altdata": 0.22, "news": 0.20, "policy": 0.10,
                   "conditions": 0.08},
}
# registry/leg key -> china_validation family (only these have a reconstructable-history harness)
_VAL_FAMILY = {"value": "valuation", "valuation": "valuation", "margin": "margin",
               "margin_detail": "margin", "news": "news_sentiment",
               # GATED Tushare legs: the `flow` convergence leg now EARNS/zeroes its weight from
               # the fundflow forward-IC family; winner_rate maps to chips for when it's scored.
               "flow": "fundflow", "winner_rate": "chips"}


def load_validation() -> dict:
    """china_validation scorecard families, or {} (accruing) on miss. Never raises."""
    try:
        from engine import china_validation
        sc = china_validation.load_scorecard()
        if sc and isinstance(sc.get("families"), dict):
            return sc["families"]
        if sc and isinstance(sc.get("results"), dict):
            return sc["results"]
        return sc.get("families", {}) if isinstance(sc, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def leg_weights_for(consumer: str) -> dict:
    """Earned, forward-return-validated leg weights for a consumer (altdata|conviction).
    Starts from the prior; a leg whose china_validation family is PROVEN wrong-sign (ic<0 with
    |t|>=2 over >=120 obs) is ZEROED (it actively misleads); a proven right-sign family is scaled
    up to 1.5x by confidence; unvalidated/accruing legs keep the prior (context floor). Renormalized.
    Returns {} for an unknown consumer so callers fall back to their own default."""
    base = dict(_PRIORS.get(consumer) or {})
    if not base:
        return {}
    fams = load_validation()
    try:
        from engine.china_validation import _MIN_PROVEN_N_TS as _MIN_N
    except Exception:  # noqa: BLE001
        _MIN_N = 25
    for leg in list(base):
        fam = fams.get(_VAL_FAMILY.get(leg, "")) if _VAL_FAMILY.get(leg) else None
        if not fam:
            continue                      # no harness for this leg → keep prior (floor)
        # china_validation writes mean_ic / t_hac / sign_ok / proven (NOT 'ic'); sign is judged
        # by the harness against the family's sign_expected, so trust sign_ok + proven here.
        ic = fam.get("mean_ic", fam.get("ic"))
        t = fam.get("t_hac")
        n = fam.get("n_obs") or 0
        sign_ok = fam.get("sign_ok")
        proven = fam.get("proven")
        try:
            ic = float(ic) if ic is not None else None
            t = float(t) if t is not None else 0.0
        except (TypeError, ValueError):
            continue
        if proven and sign_ok:
            base[leg] *= min(1.5, 1.0 + abs(ic or 0.0) * 5.0)        # earned boost
        elif sign_ok is False and abs(t) >= 2.0 and n >= _MIN_N:
            base[leg] = 0.0                                          # demonstrably wrong-sign → drop
        # else: accruing / insufficient evidence → keep the prior (context floor)
    tot = sum(base.values())
    if tot <= 0:
        return dict(_PRIORS.get(consumer) or {})         # never zero everything
    return {k: round(v / tot, 4) for k, v in base.items()}


def signal_weights() -> dict:
    """All consumers' earned leg weights, for display + the conviction composite."""
    return {c: leg_weights_for(c) for c in _PRIORS}

# (key, name_en, name_zh, tier, wired, note_en, note_zh)
CHINA_REGISTRY: list[tuple] = [
    # --- SCORED: validated regime de-risk legs in china_masterminds ----------- #
    ("credit_impulse", "Credit impulse (TSF)", "信用脉冲(社融)", "scored",
     "china_masterminds REGIME 0.45",
     "12m-sum TSF YoY 6m-change; the canonical China leading indicator.",
     "社融12个月滚动同比的6个月变化；中国经典领先指标。"),
    ("vol_regime", "Realized-vol regime (CSI 300)", "已实现波动率区制(沪深300)", "scored",
     "china_masterminds REGIME 0.35",
     "21d realized vol vs its 5y percentile (Moreira-Muir vol-managed de-risk).",
     "21日已实现波动率相对5年分位（Moreira-Muir波动管理降险）。"),
    ("margin_euphoria", "Margin euphoria", "融资亢奋", "scored",
     "china_masterminds REGIME 0.20",
     "Whole-market financing as % of float, 5y percentile — euphoria de-risk.",
     "全市场融资占流通市值比的5年分位——亢奋降险。"),
    # --- CONFIRMER: validated stock-selection edges -------------------------- #
    ("reversal", "Mean-reversion (3mo within-sector)", "均值回归(3月行业内)", "confirmer",
     "china_reversal screener",
     "Deep within-sector dips; the one A-share factor that survived Phase-0.",
     "行业内深度回调；唯一通过Phase-0的A股因子。"),
    ("lowvol", "Low-vol defensive sleeve", "低波防御组", "confirmer",
     "china_lowvol screener",
     "Lowest trailing-vol names; the low-vol anomaly holds on A-shares.",
     "最低波动名单；低波异象在A股成立。"),
    # --- DISPLAY: honest context, no validated edge -------------------------- #
    ("southbound", "Stock-Connect southbound flow", "南向资金流", "display",
     "china.html internals",
     "Mainland→HK net flow z-score; context, failed incremental Phase-0.",
     "内地→港净流入z值；背景，增量Phase-0未通过。"),
    ("ah_premium", "A/H premium", "A/H溢价", "display", "china.html internals",
     "Cross-market risk-appetite gauge; mean-reverting, not a timer.",
     "跨市场风险偏好计；均值回归，非择时。"),
    ("limit_breadth", "Limit-up/down breadth", "涨跌停宽度", "display", "china.html internals",
     "Best high-frequency A-share speculation thermometer (short retention).",
     "最佳高频A股投机温度计（保留期短）。"),
    ("etf_shares", "ETF share creations", "ETF份额变化", "display", "china.html internals",
     "Broad/sector ETF creations — a national-team tell, not separable.",
     "宽基/行业ETF申购——国家队迹象，不可分离。"),
    ("analyst", "Sell-side consensus", "卖方一致预期", "display", "china_altdata convergence",
     "Coverage + buy/hold/sell; near-universally 'buy' in China — weak signal.",
     "覆盖度+买入/中性/卖出；中国近乎全『买入』——弱信号。"),
    ("valuation", "Own-history valuation band", "自身估值分位", "display", "china_altdata convergence",
     "PE/PB/PS vs own 5y band; A-share cross-sec value Sharpe is negative.",
     "PE/PB/PS相对自身5年带；A股横截面价值夏普为负。"),
    ("margin_detail", "Per-name financing trend", "个股融资趋势", "display", "china_altdata convergence",
     "20d financing-balance change — leverage/accumulation backdrop.",
     "20日融资余额变化——杠杆/吸筹背景。"),
    # --- PENDING: Phase-0 candidates, accruing history ----------------------- #
    ("convergence", "Per-ticker alt-data convergence", "个股另类数据共振", "pending",
     "china_altdata.by_ticker",
     "Rank-aggregate of analyst+value+margin; display join, Phase-0 candidate.",
     "分析师+估值+融资的排名聚合；展示性合并，Phase-0候选。"),
    ("southbound_name", "Southbound per-name accumulation", "南向个股吸筹", "pending",
     "hk_southbound/holdings (accruing)",
     "Per-stock mainland ownership momentum; history accruing for validation.",
     "个股内地持股动量；正在累计历史以待验证。"),
    # --- PREMIUM Tushare feeds (GATED on TUSHARE_TOKEN) — display until validated ---- #
    ("flow", "Main-force money flow (主力资金, Tushare)", "主力资金流向", "pending",
     "china_altdata convergence (0.18)",
     "超大单+大单 net inflow — the push2 replacement (IP-reliable); scored only after validation.",
     "超大单+大单净流入——push2替代（全球IP可达）；验证通过后方可评分。"),
    ("winner_rate", "Holder cost-basis & win-rate (筹码, Tushare)", "筹码胜率", "pending",
     "tushare_chips (cyq_perf) — collected, surface/score after Phase-0",
     "% of float in profit + weighted holding cost; collected + accruing, not yet surfaced or scored.",
     "获利盘占比+加权持仓成本；已采集并累计，尚未展示或评分。"),
    ("broker_gold", "Broker monthly gold-stock picks (券商金股, Tushare)", "券商金股", "display",
     "tushare_broker → china_altdata desk panel",
     "Count of distinct brokers picking a name this month; discrete conviction, not the ~97%-buy ratings.",
     "当月推荐该股的券商家数；离散信心，区别于近97%『买入』评级。"),
    ("forecast_surprise", "Earnings guidance & forecast revision (业绩预告, Tushare)", "业绩预告/盈利预测", "pending",
     "tushare_forecast (forecast / report_rc) — collected, surface/score after Phase-0",
     "Company guidance direction + sell-side EPS-revision momentum; collected + accruing, not yet surfaced or scored.",
     "公司业绩预告方向+卖方盈利预测修正动量；已采集并累计，尚未展示或评分。"),
    # --- NEW US-parity alt-data legs (Stage 3d) — accruing / display ---------- #
    ("comment", "Crowd attention & inst-participation (千股千评)", "千股千评", "pending",
     "china_altdata convergence (0.15)",
     "Eastmoney 关注指数 + 机构参与度 + 主力成本; retail-vs-institutional crowding.",
     "关注指数+机构参与度+主力成本；散户与机构的拥挤度。"),
    ("lhb_inst", "Dragon-Tiger institutional seats (龙虎榜)", "龙虎榜机构席位", "pending",
     "china_altdata convergence (0.10) + discovery",
     "Institutional-seat net buy on the abnormal-move board — leading smart money.",
     "龙虎榜机构席位净买入——领先主力资金。"),
    ("block_premium", "Block-trade premium/discount (大宗交易)", "大宗交易折溢价", "pending",
     "china_altdata convergence (0.05) + discovery",
     "Off-market block premium=conviction handoff / discount=institutional unload.",
     "大宗溢价=承接 / 折价=机构出货。"),
    ("buyback", "Corporate buybacks (回购)", "回购", "display",
     "china_discovery confirmer",
     "In-progress buyback %-of-shares + RMB; insider conviction + valuation floor.",
     "在实施回购占比与金额；管理层信心+估值底。"),
    ("attention_velocity", "Attention/LHB velocity", "关注度/龙虎榜动量", "pending",
     "china_velocity (accruing)",
     "Momentum of attention + Dragon-Tiger appearances; accruing forward track record.",
     "关注度与龙虎榜上榜的动量；正在累计前瞻战绩。"),
    ("multi_leg_crowding", "Multi-leg fragility (k-of-5)", "多腿脆弱性", "display",
     "china_crowding flag",
     "Margin+pledge+limit-up+attention+valuation conjunction; contrarian risk, not scored.",
     "两融+质押+涨停+关注度+估值的合取；逆向风险，不评分。"),
    ("discovery", "Off-desk leading accumulation", "未上桌的领先吸筹", "pending",
     "china_discovery",
     "Names with ≥2 leading legs (LHB-inst/block/buyback/attention) before price confirms.",
     "在价格确认前出现≥2个领先腿（机构席位/大宗/回购/关注度）的个股。"),
    # --- KILLED: tested, no edge -------------------------------------------- #
    ("xmom", "Cross-sectional momentum", "横截面动量", "killed", "—",
     "A-share IC negative; only short-term reversal survives.",
     "A股IC为负；仅短期反转有效。"),
    ("xvalue", "Cross-sectional value", "横截面价值", "killed", "—",
     "A-share value Sharpe -0.46 — display-only, never scored.",
     "A股价值夏普-0.46——仅展示，绝不评分。"),
]


def build_china_scorecard() -> dict:
    """Group the registry by tier with counts. Pure, no compute. Never raises."""
    rows = []
    for key, en, zh, tier, wired, note_en, note_zh in CHINA_REGISTRY:
        rows.append({"key": key, "name_en": en, "name_zh": zh, "tier": tier,
                     "wired": wired, "note_en": note_en, "note_zh": note_zh})
    # attach COMPUTED forward-return stats (china_validation) onto matching rows
    fams = load_validation()
    for r in rows:
        fam = fams.get(_VAL_FAMILY.get(r["key"], "")) if _VAL_FAMILY.get(r["key"]) else None
        if fam:
            r["computed"] = {"ic": fam.get("mean_ic", fam.get("ic")), "t_hac": fam.get("t_hac"),
                             "n_obs": fam.get("n_obs"), "status": fam.get("status"),
                             "sign_ok": fam.get("sign_ok"), "proven": fam.get("proven")}
    by_tier = {t: [r for r in rows if r["tier"] == t] for t in TIERS}
    return {
        "schema": SCHEMA, "is_context_only": True,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tiers": by_tier,
        "summary": {t: len(by_tier[t]) for t in TIERS},
        "weights": signal_weights(),
        "validation_families": sorted(fams.keys()) if fams else [],
    }
