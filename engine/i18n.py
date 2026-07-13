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
    "strengthening": "走强",
    "rising": "上行",
    "falling": "下行",
    "flat": "持平",
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
    "UNCONFIRMED TURN": "未确认转向",
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
    "HALF SIZE": "半仓",
    "WATCH": "观察",
    "WAIT": "等待",
    "SELL / REDUCE": "卖出／减仓",
    "BOUNCE — HIGH RISK": "反弹 — 高风险",
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
    # discovery thematic baskets (config.yml themes.*.name)
    "Nuclear & SMR Power": "核电与小型模块化反应堆",
    "Rare Earth & Critical Minerals": "稀土与关键矿产",
    "Data Center Power & Cooling": "数据中心供电与散热",
    "Memory, HBM & Storage": "存储、HBM 与存储设备",
    "AI Semiconductors": "AI 半导体",
    "Semiconductor Equipment (WFE)": "半导体设备（WFE）",
    "Cybersecurity": "网络安全",
    "GLP-1 / Obesity": "GLP-1／减肥药",
    "Defense & Aerospace": "国防与航空航天",
    "Copper, Steel & Electrification": "铜、钢与电气化",
    "Solar": "光伏",
    "Robotics & Automation": "机器人与自动化",
    "Fintech & Payments": "金融科技与支付",
    "Medical Devices": "医疗器械",
    "Diagnostics & Life-Science Tools": "诊断与生命科学工具",
    "Agriculture & Fertilizer": "农业与化肥",
    "Space & Satellites": "航天与卫星",
    "Grid & Electrification": "电网与电气化",
    # equity factor labels (engine/equity_factors.FACTOR_LABELS — factors page + macro badges)
    "Profitability": "盈利能力",
    "Quality": "质量",
    "Investment": "投资",
    "Shareholder yield": "股东收益率",
    "Low volatility": "低波动",
    "Low beta (BAB)": "低贝塔 (BAB)",
    "Low short interest": "低做空兴趣",
    "Low accruals": "低应计",
    "Earnings momentum (SUE)": "盈利动量 (SUE)",
    # commodity-page upcoming-catalyst labels + type chips (engine/event_calendar)
    "FOMC decision": "美联储决议",
    "OPEC ministerial meeting": "OPEC 部长级会议",
    "EIA crude/petroleum inventories": "EIA 原油／石油库存",
    "FOMC": "美联储",
    "EIA WPSR": "EIA 周报",
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
    "Russell 2000": "罗素2000",
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
    # --- Hong Kong / Hang Seng dashboard vocabulary -----------------------------
    "Hong Kong": "香港",
    "Hang Seng": "恒生",
    "Hang Seng Index": "恒生指数",
    "Hang Seng Regime": "恒生周期",
    "Hong Kong Regime": "香港周期",
    "HSCEI (H-shares)": "国企指数（H股）",
    "H-shares": "H股",
    "HS China-Affiliated": "红筹股",
    "HS TECH": "恒生科技",
    "HS TECH ETF": "恒生科技ETF",
    "Tracker Fund (HSI)": "盈富基金",
    "Global Risk": "全球风险",
    "Global Risk Overlay": "全球风险叠加",
    "Risk-on": "风险偏好",
    "Risk-off": "风险规避",
    "HKD peg": "港元联系汇率",
    "Peg pressure": "联系汇率压力",
    "Dual liquidity": "双重流动性",
    "MSCI EM ETF": "新兴市场ETF",
    "MSCI EM": "新兴市场",
    # HK sector (basket) names — config hk.sectors keys
    "Internet & Tech": "互联网与科技",
    "Financials & Banks": "金融与银行",
    "Insurance": "保险",
    "Property": "地产",
    "Consumer": "消费",
    "Healthcare & Pharma": "医疗与制药",
    "Auto & EV": "汽车与新能源车",
    "Telecom & Utilities": "电信与公用事业",
    "Gaming & Leisure": "博彩与休闲",
    "Exchange & Diversified": "交易所与综合企业",
    # HK global-risk factor labels (engine.hk_global.FACTOR_LABELS)
    "US Dollar (DXY)": "美元指数（DXY）",
    "Volatility (VIX)": "波动率（VIX）",
    "Copper / Gold": "铜金比",
    "USD / CNY": "美元兑人民币",
    "EM equity (EEM)": "新兴市场股票（EEM）",
    # HK peg states (risk_state Risk-on/Risk-off/Neutral already mapped above)
    "easing": "宽松",
    "tightening": "收紧",
    "weak-side (outflow)": "弱方（资金流出）",
    "strong-side (inflow)": "强方（资金流入）",
    "mid-band": "区间中部",
    # Forex Vector — factor-group headers (research/FOREX_DASHBOARD.md)
    "Trend & Structure": "趋势与结构",
    "Carry & Rates": "套息与利率",
    "Risk & Positioning": "风险与持仓",
    "Value": "估值",
    "Shocks": "冲击",
    # Forex Vector — archetype board sections
    "Majors": "主要货币",
    "Commodity dollars": "商品货币",
    "Haven-funders": "避险/融资货币",
    "Emerging markets": "新兴市场",
    # Forex Vector — dollar-smile regimes + risk state (hub card)
    "Risk-off haven bid": "避险买盘",
    "US growth premium": "美国增长溢价",
    "Global reflation": "全球再通胀",
    "US-specific stress": "美国自身风险",
    "risk-on": "偏好风险",
    "risk-off": "避险",
    # Bonds & bond-health dashboard (research/BOND_HEALTH_DASHBOARD.md)
    "Bonds": "债券",
    "Bonds & Bond Health": "债券与债券健康",
    "Bond Health": "债券健康",
    "healthy": "健康",
    "mixed": "中性",
    "stressed": "承压",
    "recession": "衰退",
    "Recession": "衰退",
    "Drawdown": "回撤",
    "Rates vol": "利率波动",
    "Plumbing": "资金管道",
    # Macro regime prose phrases (board/chips path — rates transmission + real yields)
    "Restrictive real yields": "实际收益率偏紧",
    "Deep contraction (easing)": "深度收缩（宽松中）",
    # Fear <-> Euphoria synthesis panel (DISPLAY-ONLY, research/FEAR_EUPHORIA_PANEL_SPEC.md)
    # NB: unknown / risk-on / risk-off / mixed are already mapped above.
    "stand_aside": "观望",
    "buyable_washout": "可买入的错杀",
    "put-present": "托底在位",
    "put-absent": "托底缺失",
    "calm": "平静",
    "diversified": "分散",
    "converging": "趋同",
    "concentrated": "集中",
    # --- Canada / S&P/TSX dashboard vocabulary ----------------------------------
    "Canada": "加拿大",
    "Canada Regime": "加拿大周期",
    "S&P/TSX Regime": "标普/TSX 周期",
    "S&P/TSX Composite": "标普/TSX 综合指数",
    "S&P/TSX 60": "标普/TSX 60",
    "Bank of Canada": "加拿大央行",
    "BoC stance": "央行立场",
    "BoC policy rate": "央行政策利率",
    "Commodity / CAD overlay": "大宗商品／加元叠加",
    "Terms of trade": "贸易条件",
    "improving": "改善",
    "deteriorating": "恶化",
    "Base Metals": "基本金属",
    "Gold Miners": "黄金矿业",
    "WTI crude oil": "WTI 原油",
    "USD / CAD": "美元兑加元",
    "GoC curve": "加债收益率曲线",
    "Household debt": "家庭债务",
    "Housing": "房地产",
    # --- China Intelligence powerhouse (news / alt-data / policy / radar / bus) ----
    "China News": "中国财经新闻",
    "China Intelligence": "中国情报中心",
    "Central Bank & Policy Watch": "央行与政策观察",
    "PBoC & Policy Watch": "央行与政策观察",
    "Alternative Data": "另类数据",
    "Alternative Data Desk": "另类数据台",
    "Divergence Radar": "背离雷达",
    "Stock Connect": "互联互通",
    # news media-sentiment bands (china_news_intel)
    "supportive": "偏积极",
    "cautious": "偏谨慎",
    "steady": "平稳",
    "building": "积累中",
    "Media sentiment": "媒体情绪",
    "Policy tone": "政策基调",
    # PBoC stance (china_pboc_stance) — easing/neutral/tightening already mapped lower-case
    "Easing": "宽松",
    "Tightening": "收紧",
    "On hold": "按兵不动",
    "Rate corridor": "利率走廊",
    "Liquidity operations": "流动性操作",
    "FX fixing": "人民币中间价",
    "FX reserves": "外汇储备",
    "Reverse repo (7d)": "7天逆回购",
    # divergence radar verdicts
    "Positive divergence": "正向背离",
    "Negative divergence": "负向背离",
    "In line": "一致",
    "Silent": "无信号",
    # alt-data convergence
    "Convergence": "共振",
    "Smart-money convergence": "主力共振",
    "Accumulation": "吸筹",
    "Distribution": "派发",
    "Crowded": "拥挤",
    # --- China W8 cockpit — finite-vocab enums (who_controls, policy_impulse, risk,
    #     participation regime).  Used in china.html.j2 + china_mechanics.html.j2 chips.
    # who_controls
    "institutional": "机构控盘",
    "offshore": "外资控盘",
    "retail": "散户控盘",
    "margin": "融资盘控盘",
    # policy_impulse  (easing/tightening already mapped above)
    "targeted support": "定向支持",
    "market rescue": "救市",
    "neutral": "中性",
    # risk environment
    "frothy": "泡沫化",
    "fire sale": "恐慌抛售",
    "normal": "正常",
    # participation regime labels (used as .title() → capitalised first word)
    "Retail Ignition": "散户点火",
    "Margin Acceleration": "杠杆加速",
    "Broad Mania": "全面亢奋",
    "Forced Deleveraging": "强制去杠杆",
    "Unclear": "不明朗",
}
