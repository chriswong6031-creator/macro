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

SCHEMA = "china_signal_lab.v1"

TIERS = ("scored", "confirmer", "display", "pending", "killed")

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
    by_tier = {t: [r for r in rows if r["tier"] == t] for t in TIERS}
    return {
        "schema": SCHEMA, "is_context_only": True,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tiers": by_tier,
        "summary": {t: len(by_tier[t]) for t in TIERS},
    }
