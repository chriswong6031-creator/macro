"""Bilingual (EN ↔ 中文) helpers for the static dashboards.

The site ships BOTH languages in the DOM and toggles visibility with CSS
(`html[data-lang="zh"] .l-en{display:none}` etc., in templates/theme.css), so the
language switch is instant and needs no rebuild. This module is the Python side:

  * `t(en, zh)` — dual-language inline markup for strings composed in Python.
  * `tr(en)`    — look up the canonical Chinese for a finite-vocab English label
                  (falls back to the English itself when unknown).
  * `td(en)`    — `t(en, tr(en))`: wrap a dynamic English label as a bilingual
                  span using the glossary. Exposed to templates as a global so
                  `{{ td(latest.quad_name) }}` just works for the at-a-glance
                  vocabulary (regimes, states, postures, sectors, …).

Templates also have an equivalent `t()` Jinja macro for literal pairs. Both return
markup that is safe under autoescape (build_vector) and inert without it
(build_site). Canonical terms also live in research/I18N_GLOSSARY.md.
"""
from __future__ import annotations

from markupsafe import Markup


def t(en: str, zh: str | None = None) -> Markup:
    """Inline dual-language span. `zh` falls back to `en` when omitted."""
    zh = en if zh is None else zh
    return Markup('<span class="l-en">{}</span><span class="l-zh">{}</span>').format(en, zh)


def tr(en: str) -> str:
    """Canonical Chinese for a finite-vocab English label, else the English."""
    if en is None:
        return en
    return LEX.get(en, LEX.get(en.strip(), en))


def td(en: str) -> Markup:
    """Bilingual span for a dynamic English label, via the glossary."""
    return t(en, tr(en))


# --------------------------------------------------------------------------- #
# Glossary of finite display vocabulary (English label -> Chinese). Free-form
# composed sentences are translated at their source, not here.
# --------------------------------------------------------------------------- #
LEX: dict[str, str] = {
    # regimes / quadrants (both long and short forms)
    "Goldilocks": "理想增长",
    "Reflation": "再通胀",
    "Stagflation": "滞胀",
    "Growth-scare/Deflation": "增长恐慌／通缩",
    "Growth scare": "增长恐慌",
    "Growth-scare": "增长恐慌",
    "Deflation": "通缩",
    # transition radar states
    "STABLE": "稳定",
    "WEAKENING": "走弱",
    "TRANSITIONING": "转换中",
    "NEW REGIME": "新周期",
    "NEW_REGIME": "新周期",
    # Fed-liquidity overlay
    "expanding": "扩张",
    "neutral": "中性",
    "contracting": "收缩",
    "unknown": "未知",
    # business-cycle tag
    "early": "早期",
    "mid": "中期",
    "late": "晚期",
    "overdue": "逾期",
    # exposure-dial posture
    "AGGRESSIVE": "进取",
    "CONSTRUCTIVE": "偏多",
    "NEUTRAL": "中性",
    "CAREFUL": "谨慎",
    "DEFENSIVE": "防御",
    # heat-board bands
    "OVERHEATED": "过热",
    "HOT": "偏热",
    "COLD": "偏冷",
    # rotation stages
    "leading": "领先",
    "weakening": "走弱",
    "improving": "改善",
    "lagging": "落后",
    # cycle-ladder state labels (STATE_DISPLAY 'label')
    "DOWNTREND": "下跌趋势",
    "NEARING A LOW": "接近低点",
    "BOTTOMING": "筑底中",
    "BUY ZONE": "买入区",
    "UPTREND": "上涨趋势",
    "NEARING A HIGH": "接近高点",
    "TOPPING": "做顶中",
    "COUNTER-TREND BOUNCE": "逆势反弹",
    # cycle-ladder actions (STATE_DISPLAY 'action')
    "AVOID": "回避",
    "GET READY": "准备",
    "BUY SETUP": "买入预备",
    "BUY": "买入",
    "HOLD": "持有",
    "TAKE PROFITS": "止盈",
    "SELL SETUP": "卖出预备",
    # entry-timing headlines
    "BUY NOW": "立即买入",
    "BUY SOON": "即将买入",
    "WATCH": "观察",
    "WAIT": "等待",
    "SELL / REDUCE": "卖出／减仓",
    # action-board conflict tags
    "WATCH — DON'T BUY YET": "观察 — 暂不买入",
    "DON'T CHASE": "勿追高",
    "TOO EARLY": "过早",
    "REGIME-TAPE CONFLICT": "周期与盘面冲突",
    # sector category names (tickers stay English)
    "Materials": "原材料",
    "Communications": "通讯",
    "Energy": "能源",
    "Financials": "金融",
    "Industrials": "工业",
    "Technology": "科技",
    "Consumer Staples": "必需消费",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
    "Health Care": "医疗保健",
    "Consumer Discretionary": "可选消费",
    "Semiconductors": "半导体",
    "Small Caps": "小盘股",
    "Equal-Weight S&P": "等权标普",
    "Quality factor": "质量因子",
    "Momentum factor": "动量因子",
    "Min-vol factor": "低波因子",
    "IG Corporate Bonds": "投资级公司债",
    "Gold": "黄金",
    # product / page names
    "Macro Vector": "宏观向量",
    "Bitcoin Vector": "比特币向量",
    "Market Intelligence": "市场情报",
    # Bitcoin Vector signal vocabulary
    "bull": "看多",
    "bear": "看空",
    "high_risk": "高风险",
    "low_risk": "低风险",
    "broken": "走坏",
    "constructive": "偏多",
    "positive": "正向",
    "negative": "负向",
    "Defensive": "防御",
    "Fragile": "脆弱",
    "Recovery": "复苏",
    "Expansion": "扩张",
    "Strategic": "战略",
    "Tactical": "战术",
    "Alts": "山寨币",
    "Risk ON": "风险开启",
    "Risk OFF": "风险关闭",
    "ON": "开启",
    "OFF": "关闭",
    "Low Risk": "低风险",
    "High Risk": "高风险",
    # Vector hero metric words
    "Strong": "强",
    "Weak": "弱",
    "Low": "低",
    "High": "高",
    "Normal": "正常",
    "Sweet spot": "理想区间",
    "Upside": "上行",
    "Downside": "下行",
    "Inflow": "流入",
    "Outflow": "流出",
    # cross-asset map group headers + capitalised trend words
    "Index": "指数",
    "Commodities": "大宗商品",
    "Crypto": "加密货币",
    "Bull": "看多",
    "Bear": "看空",
    "Neutral": "中性",
    # calibration verdict words
    "CONFIRMED": "已确认",
    "DIRECTIONAL": "有方向性",
    "CONTEXT": "仅作背景",
    "CONTRARIAN": "逆向",
    # commodity + cross-asset proper names (shown as labels)
    "Crude Oil": "原油",
    "Oil": "原油",
    "Copper": "铜",
    "US Dollar": "美元",
    "Silver": "白银",
    "Brent Oil": "布伦特原油",
    "Nasdaq": "纳斯达克",
    "Dow Jones": "道琼斯",
    "S&P 500": "标普500",
    "DXY": "美元指数",
    # --- China A-share dashboard vocabulary -------------------------------------
    "China A-shares": "中国A股",
    "China A-Share Regime": "中国A股周期",
    "Shanghai Composite": "上证综指",
    "Shenzhen Component": "深证成指",
    "CSI 300": "沪深300",
    "A-shares": "A股",
    "PBoC stance": "央行立场",
    "Northbound": "北向资金",
    "Southbound": "南向资金",
    "Large-cap breadth": "大盘宽度",
    # China sector names (config china.yahoo.sector_etfs)
    "Banks": "银行",
    "Securities & Brokers": "券商",
    "Baijiu & Liquor": "白酒",
    "Healthcare": "医疗",
    "Innovative Drugs": "创新药",
    "New-Energy Vehicle": "新能源车",
    "Solar & Photovoltaic": "光伏",
    "Defense & Military": "国防军工",
    "Nonferrous Metals": "有色金属",
    "Coal": "煤炭",
    "Automobiles": "汽车",
    "Media": "传媒",
}
