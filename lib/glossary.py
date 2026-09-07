"""Frozen, source-bound view-model for the public /glossary directory.

Mirrors ``lib/help_directory.py``: this module mints no new term, no new
score, no new stat. Every entry is bound to an existing heading in
``docs/site_semantics/*.md`` — a term is either complete against its named
source line, or the whole directory refuses to render (fail-closed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RELATIVE_HREF_RE = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9][A-Za-z0-9._/-]*\.html"
    r"(?:\?[A-Za-z0-9._~!$&'()*+,;=@%/-]*)?$"
)

GLOSSARY_MIN_TERMS = 50

BANNED_GLANCE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"[`_]"),
    re.compile(r"\b(?:engine|scripts|lib|templates|docs|config)/"),
    re.compile(r"\.(?:py|json|j2|parquet|yml|yaml|md)\b"),
    re.compile(r"\bz-scores?\b", re.I),
    re.compile(r"(?<![A-Za-z])pp(?![A-Za-z])"),
)

BANNED_GLANCE_TOKENS: frozenset[str] = frozenset(
    """
    RISK_OFF RISK_ON NEW_REGIME TRANSITIONING WEAKENING STABLE
    US_PROFILE CN_PROFILE WEIGHTS Tier-A T1 T2 T3 T4 VRP SUE
    conviction_pp selection_pp weighted_usd weighted_n weight_receipt
    raw_quad pending_quad transition_state overextended
    """.split()
)


@dataclass(frozen=True, slots=True)
class GlossaryDomain:
    id: str
    label_en: str
    label_zh: str
    source_file: str
    page_href: str


GLOSSARY_DOMAINS: tuple[GlossaryDomain, ...] = (
    GlossaryDomain("macro", "Macro", "宏观", "docs/site_semantics/macro.md", "macro.html"),
    GlossaryDomain("us-stocks", "US stocks", "美股", "docs/site_semantics/us_stocks.md", "us_stocks.html"),
    GlossaryDomain("china", "China", "中国", "docs/site_semantics/china.md", "china.html"),
    GlossaryDomain("china-stocks", "China stocks", "中国个股", "docs/site_semantics/china_stocks.md", "china_stocks.html"),
    GlossaryDomain("etfs", "Fund flows", "基金流向", "docs/site_semantics/etfs.md", "etfs.html"),
    GlossaryDomain("signals", "Signal quality", "信号质量", "docs/site_semantics/stretch_oracles.md", "measurement.html"),
)
_DOMAIN_IDS = frozenset(d.id for d in GLOSSARY_DOMAINS)


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    id: str
    domain: str
    name_en: str
    name_zh: str
    answer_en: str
    answer_zh: str
    source_file: str
    source_line: int
    source_heading: str
    page_href: str
    page_en: str
    page_zh: str
    why_en: str | None = None
    why_zh: str | None = None


_MACRO = ("macro.html", "Macro dashboard", "宏观仪表盘")
_US = ("us_stocks.html", "US stocks dashboard", "美股仪表盘")
_CHINA = ("china.html", "China dashboard", "中国仪表盘")
_CN_STOCKS = ("china_stocks.html", "China stock screener", "中国个股筛选")
_ETFS = ("etfs.html", "Fund flows dashboard", "基金流向仪表盘")
_SIGNALS = ("measurement.html", "Calibration Lab", "校准实验室")


def _t(id_, domain, name_en, name_zh, answer_en, answer_zh, source_file, source_line,
       source_heading, page, why_en=None, why_zh=None) -> GlossaryTerm:
    href, page_en, page_zh = page
    return GlossaryTerm(
        id=id_, domain=domain, name_en=name_en, name_zh=name_zh,
        answer_en=answer_en, answer_zh=answer_zh,
        source_file=source_file, source_line=source_line, source_heading=source_heading,
        page_href=href, page_en=page_en, page_zh=page_zh,
        why_en=why_en, why_zh=why_zh,
    )


_M = "docs/site_semantics/macro.md"
_UST = "docs/site_semantics/us_stocks.md"
_CH = "docs/site_semantics/china.md"
_CHS = "docs/site_semantics/china_stocks.md"
_ET = "docs/site_semantics/etfs.md"
_ORA = "docs/site_semantics/stretch_oracles.md"

GLOSSARY_TERMS: tuple[GlossaryTerm, ...] = (
    _t("market-state-score", "macro", "Market State Score", "市场状态分",
       "A 0–100 read of how the US market is behaving right now — risk-on, mixed, or risk-off. It confirms the tape; it does not forecast it.",
       "0–100 的读数，说明美股当下的状态：风险偏好、混合或避险。它确认当前走势，而不是预测未来。",
       _M, 9, "Market State Score / Verdict (hero)", _MACRO,
       "Green means trend-follow. Yellow means size smaller. Red means defend capital first.",
       "绿色顺势加仓，黄色减小仓位，红色优先保住本金。"),
    _t("macro-regime-quadrant", "macro", "Macro Regime Quadrant", "宏观周期象限",
       "Which of four backdrops the market is trading in, set by whether growth and inflation are rising or falling.",
       "决定市场所处的四种经济环境之一，取决于经济增长与通胀是上升还是下降。",
       _M, 18, "Macro Regime Quadrant (hero sub-line + stocks header badge)", _MACRO,
       "Use it for sector and style tilts, not for timing the market itself.",
       "用于板块与风格配置，而非判断大盘拐点。"),
    _t("transition-state", "macro", "Regime Stability Read", "周期稳定度",
       "How settled the current economic backdrop is — freshly confirmed, holding steady, showing early cracks, or just changed.",
       "说明当前经济环境有多稳定：刚确认、保持稳定、出现裂痕，还是刚刚转变。",
       _M, 28, "Transition State / Stability Sub-line (hero)", _MACRO,
       "A just-changed reading means wait for confirmation before making big bets.",
       "刚转变时，应等待确认后再下重注。"),
    _t("pullback-risk-radar", "macro", "Pullback Risk Radar", "回撤风险雷达",
       "An early warning on the odds of a sharp drop, built from seven kinds of market scare. It advises on size, not on what to own.",
       "对急跌概率的早期预警，综合七类市场恐慌迹象，用于调整仓位大小，而非决定买什么。",
       _M, 37, "Risk Radar (hero context line / click-through dialog)", _MACRO,
       "A higher reading means trade smaller — not necessarily sell.",
       "读数越高，仓位应越小——不一定要清仓。"),
    _t("fired-alerts-pill", "macro", "Fired Alerts", "已触发提醒",
       "A count of live alerts that just changed state — a level shift, a crossing, a sign flip. Alerts fire once, not continuously.",
       "记录刚刚发生状态变化的提醒数量，如等级切换或方向翻转。提醒只在变化时触发一次。",
       _M, 46, "Fired Alerts Pill (hero)", _MACRO),
    _t("macro-backdrop-matrix", "macro", "Macro Backdrop Scorecard", "宏观背景评分表",
       "Six separate readings, each scored 0 to 100, that together make up the market state score — trend, risk appetite, volatility, participation, liquidity, and stress.",
       "构成市场状态总分的六项独立评分：趋势、风险偏好、波动、参与度、流动性与压力，各自 0 到 100 分。",
       _M, 55, "Macro Backdrop — Six-Factor Evidence Matrix (card / dialog)", _MACRO),
    _t("multi-timeframe-tape-table", "macro", "Multi-Timeframe Trend Table", "多周期趋势表",
       "The technical direction of the main US indexes across four time horizons, from daily to monthly, shown side by side.",
       "并列展示美股主要指数在日线到月线四个周期上的技术方向。",
       _M, 64, "Multi-Timeframe Tape Table (inside regime panel)", _MACRO,
       "All timeframes pointing the same way is a stronger signal than one alone.",
       "所有周期方向一致时，信号比单一周期更可靠。"),
    _t("posture-dial", "macro", "Posture Dial", "仓位姿态盘",
       "How aggressively to size positions under the current backdrop, from defensive to aggressive. It sizes risk, not which stocks to pick.",
       "说明当前环境下仓位应有多激进，从防御到进取。它决定仓位大小，而非选股。",
       _M, 73, "Posture Dial (stocks mode header / macro page hero)", _MACRO),
    _t("sector-heat-strip", "macro", "Sector Heat Strip", "板块热力条",
       "A quick snapshot of which market sectors are leading and which are lagging right now — context, not a buy signal.",
       "快速展示当前哪些板块领涨、哪些落后——仅作参考，不是买入信号。",
       _M, 82, "Sector Heat Strip (macro hero area)", _MACRO),
    _t("leadership-rotation", "macro", "Leadership & Rotation", "领涨轮动",
       "Where sector leadership is shifting today, alongside a separate check on whether previously damaged hardware-related stocks have recovered.",
       "展示当下领涨板块的变化，并单独追踪此前受损的硬件相关股票是否已修复。",
       _M, 89, "Leadership & Rotation (Risk dialog)", _MACRO),

    _t("regime-badge-us", "us-stocks", "Regime Badge", "周期徽章",
       "The same growth-and-inflation backdrop shown on the macro dashboard, filtering this whole page. It shifts slowly and describes the economy, not today's tape.",
       "与宏观仪表盘相同的增长与通胀背景，用于筛选本页内容。变化缓慢，描述的是经济而非当日走势。",
       _UST, 9, "Regime Badge (header)", _US),
    _t("posture-chip-us", "us-stocks", "Posture Chip", "姿态标签",
       "A five-level dial for how aggressively to trade the current backdrop, from defensive to aggressive. It sizes risk, not stock choice.",
       "五档姿态标签，说明当前环境下交易应有多激进，从防御到进取，决定仓位而非选股。",
       _UST, 18, "Posture Chip (header)", _US),
    _t("prophet-stock-signals-board", "us-stocks", "Stock Signals Board", "选股信号榜",
       "A shortlist of stocks whose price pattern has cleared a strict entry test, ranked by strength relative to their sector peers.",
       "一份经过严格入场检验的股票候选清单，按相对同行业的强弱排序。",
       _UST, 27, "Prophet Stock Signals Board (main section, hero card list)", _US,
       "This is a research shortlist, not a buy list — verify price and backdrop first.",
       "这是研究候选清单，不是买入清单——请先核实价格与环境。"),
    _t("alpha-chip", "us-stocks", "Relative Strength Rank", "相对强度排名",
       "How this stock's momentum compares to its sector peers after stripping out the broad market and sector moves. A better rank means stronger relative performance.",
       "剔除大盘与行业整体走势后，该股动能相对同行的排名，排名越靠前表现越强。",
       _UST, 36, "Alpha (α) Chip on Stock Cards", _US,
       "Strong relative strength with poor entry timing means a good stock at the wrong moment.",
       "相对强度强但入场时机差，意味着好股票遇上了不好的买点。"),
    _t("buy-readiness-score-us", "us-stocks", "Buy-Readiness Score", "买入准备度评分",
       "How ready a stock looks to be bought today, judged on the shape of the setup rather than on how good the company is.",
       "0–100 分，评估某股票今日的买入准备度，看的是走势形态而非公司好坏。",
       _UST, 45, "Buy-Readiness / Setup Score on Stock Cards", _US,
       "A high score is a timing read, never a recommendation to buy.",
       "高分是时机判断，而非买入建议。"),
    _t("insider-buy-chip", "us-stocks", "Insider Buying Chip", "内部人买入标签",
       "Company insiders recently bought more shares than they sold. It supports other signals but is not a standalone reason to buy.",
       "公司内部人近期净买入自家股票。可作为其他信号的佐证，但不能单独作为买入理由。",
       _UST, 54, "Insider Buy Chip (\U0001f464 chip on stock cards)", _US),
    _t("entry-timing-dot-us", "us-stocks", "Entry Timing Dot", "入场时机点",
       "Green means a defined entry is open today. Yellow means the setup is valid but the price has run too far — wait for a dip.",
       "绿色表示今日存在明确入场点。黄色表示形态成立但价格已过度上涨，需等待回落。",
       _UST, 63, "Entry Timing Dot (green / yellow / grey on stock cards)", _US,
       "Never chase an extended stock just because conviction is high.",
       "不要仅因信心高就追高已过度上涨的股票。"),
    _t("sue-earnings-chip", "us-stocks", "Earnings Surprise Chip", "财报超预期标签",
       "How far a company's latest earnings beat analyst expectations. A fresh, larger beat has historically been followed by continued price drift in that direction.",
       "衡量最新财报超出分析师预期的幅度。近期较大幅度的超预期，历史上常伴随股价延续同向走势。",
       _UST, 72, "SUE Earnings Surprise Chip on Stock Cards", _US),
    _t("sector-act-now-board-us", "us-stocks", "Sector Act-Now Table", "板块即时行动表",
       "A condensed table of only the stocks whose entry signal has actually triggered, sorted by tier and then by relative strength.",
       "仅列出已实际触发入场信号的股票，先按等级、再按相对强度排序的精简表格。",
       _UST, 81, "Sector Act-Now Board (confluence-gated table below cards)", _US),
    _t("factor-seasonality-chip", "us-stocks", "Seasonality Chip", "季节性标签",
       "Whether the current calendar month has historically been a headwind or tailwind for growth and momentum stocks. A weak, long-horizon bias only.",
       "说明本月历史上对成长与动量股是逆风还是顺风，只是一个较弱的长期参考。",
       _UST, 90, "Factor Seasonality Chip (header area, seasonal climate)", _US,
       "It can be overridden by any strong backdrop or risk signal.",
       "任何强烈的环境或风险信号都可以盖过这个季节性倾向。"),

    _t("market-state-score-china", "china", "China Market State Score", "中国市场状态分",
       "A composite read of the A-share market's current posture — green for risk-on, yellow for mixed, red for risk-off. A present-state read, not a forecast.",
       "对 A 股当下状态的综合评分：绿色偏乐观，黄色中性，红色偏悲观。这是当下状态，而非预测。",
       _CH, 8, "Market State Score (hero)", _CHINA),
    _t("regime-quadrant-pill-china", "china", "China Regime Quadrant", "中国周期象限",
       "The growth-and-inflation backdrop the A-share market sits in, plus how early or late that backdrop is in its current run.",
       "A 股所处的增长与通胀背景，以及该背景处于早期还是后期阶段。",
       _CH, 17, "Regime Quadrant Pill (hero)", _CHINA),
    _t("path-chart-china", "china", "Recent Trend Chart", "近期趋势图",
       "Whether the China market state score has been improving or deteriorating over the past two weeks. Context only, not a single-day trigger.",
       "展示中国市场状态分过去两周是在改善还是恶化，仅作参考，不作为单日交易依据。",
       _CH, 26, "11-Session Path Chart (hero)", _CHINA),
    _t("pullback-risk-radar-china", "china", "China Pullback Risk Radar", "中国回撤风险雷达",
       "The estimated probability of a sharp pullback in the next few weeks, built from six kinds of market scare. Fires loud alerts early, by design.",
       "估算未来几周内急跌的概率，综合六类市场恐慌信号，设计上会提前发出响亮警报。",
       _CH, 35, "Pullback Risk Radar (hero button / popover)", _CHINA),
    _t("what-to-do-card-china", "china", "What To Do Card", "操作建议卡",
       "The recommended trading posture for the current China backdrop — how aggressive or defensive to be with sizing. It does not name stocks.",
       "针对当前中国市场环境的建议仓位姿态——应偏进取还是防御，不涉及具体选股。",
       _CH, 44, "What To Do Card (row 1)", _CHINA),
    _t("market-tiles-china", "china", "Market Tiles", "指数速览",
       "Quick price snapshots for the four major China and Hong Kong benchmarks. For daily orientation only — never use one day's move to override the bigger read.",
       "四大中国及香港基准指数的每日价格速览，仅作当日参考，不应以单日涨跌否定大局判断。",
       _CH, 53, "Market Tiles — SSE / CSI300 / ChiNext / Hang Seng (row below hero)", _CHINA),
    _t("board-track-record-china", "china", "Board Track Record", "榜单历史战绩",
       "The share of logged picks on this board that have beaten the CSI300 index so far, with a confidence range and the number of picks counted.",
       "该榜单已记录的选股中跑赢沪深300指数的比例，附带置信区间与统计样本数量。",
       _CH, 62, "Board Track Record Strip — \"Beating CSI300 so far\" (china_stocks mode, track-record panel)", _CHINA),
    _t("sector-rotation-act-now-china", "china", "Sector Rotation Board", "板块轮动即时表",
       "Where to look and where to avoid in the A-share market right now, across four lanes from buy-now to reduce. A name can appear in two lanes.",
       "展示当下 A 股应关注与应回避的板块，分四档从建议买入到建议减仓，同一标的可能同时出现在两档中。",
       _CH, 71, "Sector Rotation Act-Now Board (china.html macro mode, four-lane table)", _CHINA),
    _t("sector-flow-velocity-china", "china", "Sector Flow Velocity", "板块资金流速",
       "How fast capital is moving into or out of each A-share sector, and whether that pace is speeding up or slowing down.",
       "衡量资金流入或流出各 A 股板块的速度，以及该速度正在加快还是放缓。",
       _CH, 80, "Sector Flow Velocity (internals section)", _CHINA),
    _t("china-setup-score", "china", "China Setup Score", "中国建仓评分",
       "How close an A-share name is to an actionable entry, blending timing, how washed-out it is, and sector tailwind. Not a win-rate.",
       "评估某只 A 股距可操作入场点的远近，综合时机、超跌程度与板块顺风，不代表胜率。",
       _CH, 89, "China Setup Score on Stock Cards (china_stocks mode)", _CHINA),

    _t("tier-cascade-cn", "china-stocks", "Entry Tier Cascade", "入场等级序列",
       "The confirmation tier for an A-share entry signal, from the freshest confirmed trigger (highest) to the earliest, weakest hint (lowest).",
       "A 股入场信号的确认等级，从最新确认的触发信号（最高）到最早最弱的迹象（最低）。",
       _CHS, 9, "T1–T4 Tier Cascade (stock cards, header)", _CN_STOCKS,
       "The top two tiers mean a confirmed entry window is open right now.",
       "最高两个等级意味着当前存在已确认的入场窗口。"),
    _t("buy-readiness-score-cn", "china-stocks", "China Buy-Readiness Score", "中国买入准备度评分",
       "How close this A-share name is to an actionable buy, blending timing, how washed-out it is, distress, and sector tailwind. Not a win-rate.",
       "评估某只 A 股距可操作买入点的远近，综合时机、超跌、风险折让与板块顺风，不代表胜率。",
       _CHS, 18, "Buy-Readiness Score on Stock Cards (china_stocks mode)", _CN_STOCKS),
    _t("board-track-record-cn", "china-stocks", "China Board Track Record", "中国榜单历史战绩",
       "The share of this board's logged picks that have beaten the CSI300 index so far, with a confidence range and sample size.",
       "该榜单已记录选股中跑赢沪深300指数的比例，附带置信区间与样本数量。",
       _CHS, 27, "Board Track Record Strip — \"Beating CSI300 so far\" (track-record panel)", _CN_STOCKS),
    _t("washout-chip", "china-stocks", "Washout Reclaim Chip", "超跌反弹标签",
       "This stock recently fell sharply then reclaimed that drop — a pattern that historically precedes durable lows more often than chance. Context, not a standalone signal.",
       "该股近期急跌后收复失地——历史上此形态较随机情形更常预示阶段性底部，仅作参考。",
       _CHS, 36, "Washout Chip on Stock Cards", _CN_STOCKS),
    _t("entry-timing-chips-cn", "china-stocks", "Entry Timing Chip", "入场时机标签",
       "Buy Now means the entry window is open today. Wait For Pullback means the signal is valid but the price has run ahead. Hold means already in position.",
       "买入表示今日入场窗口开放；等待回调表示信号有效但价格已过度上涨；持有表示已在场内。",
       _CHS, 45, "Entry Timing Chips: \"Buy Now\" / \"Wait for Pullback\" / \"Hold\"", _CN_STOCKS),
    _t("stage-labels-cn", "china-stocks", "Entry Stage Label", "入场阶段标签",
       "Entry means this name is at the cleanest point to buy. Ran Late means it appeared recently but has already moved a lot — the window has mostly passed.",
       "「入场」表示当前为最佳买点；「已迟」表示近期上榜但已大幅上涨，入场窗口已大半错过。",
       _CHS, 54, "Stage Labels: \"ENTRY\" / \"RAN LATE\" (stock cards, china_stocks mode)", _CN_STOCKS),
    _t("sector-turn-boost-chip", "china-stocks", "Sector Turn Chip", "板块转折标签",
       "This name's sector has just shown its first sign of turning up from a trough, adding a bonus tint in the screener. Display context only.",
       "该股所属板块刚出现见底回升的首个迹象，筛选表中会加以高亮，仅供参考。",
       _CHS, 63, "Sector Turn Boost Chip (table mode, stock screener)", _CN_STOCKS),
    _t("coiled-cohort-chip", "china-stocks", "Coiled Cohort Chip", "蓄势群组标签",
       "This stock belongs to a group of similar names that have compressed tightly together after a washout — a group turning together often makes a stronger move.",
       "该股属于超跌后走势收敛的一组相似标的——若整组同步反转，往往力度更强。",
       _CHS, 72, "Coiled Cohort Chip on Stock Cards", _CN_STOCKS),

    _t("consensus-board", "etfs", "Consensus Board", "共识榜单",
       "How many separately-managed funds bought or sold the same stock in the comparison window. A count is the hardest number here to game with one large fund.",
       "统计有多少家独立基金在同一窗口内买入或卖出同一只股票，这一数字最难被单一大基金操纵。",
       _ET, 26, "The Consensus Board — \"funds in\" (n accumulating / n trimming)", _ETFS),
    _t("net-conviction", "etfs", "Net Conviction", "净信心",
       "How much of the tracked funds' money moved into a name, after taking out the part that only moved because prices moved.",
       "追踪基金真正投入某只股票的资金规模，已剔除仅因价格上涨而扩大的部分。",
       _ET, 35, "Net conviction (pp)", _ETFS,
       "It separates real buying from a position that just grew with the market.",
       "它把真实买入和随行情自然变大的仓位区分开。"),
    _t("per-fund-conviction", "etfs", "Per-Fund Conviction", "单只基金信心度",
       "The same real-buying measure as net conviction, but for one fund's decision on one stock — the building block the consensus board adds up.",
       "与净信心相同的真实买入衡量，但针对单只基金对单只股票的决定——是共识榜单加总的基础单元。",
       _ET, 44, "Conviction (pp) — per fund row, \"Every add, by fund\"", _ETFS),
    _t("flow-vs-selection", "etfs", "Flow vs Selection", "资金流入与主动选股",
       "Two different reasons a fund's holding can grow: money arriving in the whole theme, or the manager actively favoring this one name over others.",
       "基金持仓增加的两种不同原因：整体主题吸引资金流入，或经理主动看好该股胜过其他标的。",
       _ET, 53, "Flow vs selection — which half of the move was investor money", _ETFS),
    _t("dollar-estimates", "etfs", "Dollar Size Estimate", "美元规模估算",
       "The size of a fund decision expressed in money rather than only in weight — the same move means very different things for a small and a large fund.",
       "以美元金额而非仅以权重表示基金决策的规模，因同样比例的变动对大小基金意义完全不同。",
       _ET, 62, "Dollar estimates (total $, flow $, selection $)", _ETFS),
    _t("measurement-windows", "etfs", "Measurement Window", "观测窗口",
       "The comparison spans a fixed number of fund filings, not a fixed number of days — since funds publish on different calendars, one window covers different real time spans.",
       "对比窗口按固定的基金披露次数计算，而非固定天数，因基金披露频率不同，同一窗口对应的实际天数也不同。",
       _ET, 92, "Measurement windows — how long \"this move\" actually is", _ETFS),
    _t("persistence-streak", "etfs", "Persistence Streak", "持续加仓天数",
       "How many filings in a row one fund kept moving the same direction on a name, and whether that pace is speeding up or slowing down.",
       "统计某基金连续多少次披露都朝同一方向操作某股票，以及这一节奏是在加快还是放缓。",
       _ET, 101, "Persistence — streak, breadth and acceleration", _ETFS),
    _t("fresh-conviction", "etfs", "Fresh Conviction", "新建仓信心",
       "A brand-new position a fund did not hold before — the highest-information kind of buy, since it cannot be explained by drift or rebalancing.",
       "基金此前完全未持有、如今新建立的仓位——信息量最高的买入类型，无法用漂移或再平衡解释。",
       _ET, 110, "Fresh conviction (brand-new positions)", _ETFS,
       "Two or more funds opening the same name together is the strongest cross-manager signal on this page.",
       "两家以上基金同时新建同一仓位，是本页最强的跨机构信号。"),
    _t("stance-line", "etfs", "Stance", "操作立场",
       "A plain instruction for what to do about a row: watch, get ready, act, protect gains, or stand aside. Filings are lagged, so the honest floor is watch, don't chase.",
       "对该行数据给出的明确建议——观察、准备、行动、保护收益或按兵不动。因基金披露有延迟，最低建议通常是观察而非追高。",
       _ET, 119, "Stance — \"what to do\" (Act · Get ready · Watch — don't chase · Protect gains · Stand aside · Ignore)", _ETFS),
    _t("hero-verdict-etfs", "etfs", "Hero Verdict Line", "顶部结论句",
       "One sentence summarizing which themes are drawing the most real fund buying right now, and whether the broader market backdrop supports or fights that buying.",
       "一句话总结当下哪些主题正获得基金真实买入，以及大盘背景是支持还是对抗这一买入。",
       _ET, 128, "Hero verdict line", _ETFS),
    _t("rotation-backdrop", "etfs", "Rotation Backdrop", "轮动背景",
       "What the broader market has been rewarding lately, shown as context for the fund decisions above — it never re-ranks any name on the board.",
       "展示近期大盘整体青睐的方向，仅作为上方基金决策的背景参考，不会改变榜单排序。",
       _ET, 146, "The rotation backdrop — \"the market they're buying into\"", _ETFS),
    _t("fund-coverage-table", "etfs", "Fund Coverage Table", "基金覆盖情况表",
       "How much history exists for each fund and how current its latest filing is, measured against the newest filing in the whole tracked group.",
       "展示每只基金已有多少历史数据，以及其最新披露相对于全体跟踪基金中最新一次披露有多滞后。",
       _ET, 155, "Fund coverage table — snapshots, latest, freshness", _ETFS),
    _t("data-quality-guards", "etfs", "Data Quality Guards", "数据质量护栏",
       "Automatic checks that catch stock splits, broken snapshots, and duplicate filings before they can be mistaken for real buying or selling.",
       "自动检测股票拆分、异常快照与重复披露的机制，防止被误判为真实买卖行为。",
       _ET, 164, "Data-quality guards — split adjustment, quarantine, duplicate snapshots", _ETFS,
       "A missing figure here means the guard fired on purpose, not that nothing happened.",
       "此处数据缺失，是护栏主动拦截，而非代表没有发生任何操作。"),
    _t("weight-trajectory-sparkline", "etfs", "Weight Trajectory Sparkline", "持仓走势迷你图",
       "A small line showing whether one fund's position in a stock has been growing, shrinking, or flat over recent filings.",
       "小型走势图，展示某基金对某股票的持仓近期在增长、缩减还是持平。",
       _ET, 184, "Weight trajectory sparkline", _ETFS),
    _t("forward-windows-etfs", "etfs", "Forward Outcome Ledger", "后续表现记录",
       "A running record of what the board's past picks actually did afterward, against the market, over several time windows — updated nightly, never used to rank today's board.",
       "持续记录榜单过往选股在多个后续时间窗口的实际表现，每晚更新，但不用于排序当前榜单。",
       _ET, 202, "Forward windows (Calibration Lab) — what the board's names did next", _ETFS),

    _t("overextended-reading", "signals", "Overextended Reading", "超延伸读数",
       "A flag that a move has run far from its normal range. Two versions of it exist and they often disagree.",
       "标记某走势已严重偏离正常区间的信号。该信号存在两个版本，两者常常意见不一。",
       _ORA, 23, "O1 — what fires, in practice", _SIGNALS,
       "When the two disagree, treat the stretch call as unsettled.",
       "两者不一致时，应视超延伸判断为尚未明朗。"),
)


def _validate_glance_text(entry_id: str, field: str, text: str) -> None:
    for pattern in BANNED_GLANCE_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"glossary term {entry_id!r}: {field} carries banned vocabulary: {text!r}")
    tokens = re.findall(r"[A-Za-z0-9_]+", text)
    for token in tokens:
        if token in BANNED_GLANCE_TOKENS:
            raise ValueError(f"glossary term {entry_id!r}: {field} carries banned token {token!r}")


def validate_glossary(root: Path, terms: Iterable[GlossaryTerm] = GLOSSARY_TERMS) -> None:
    """Fail closed when a glossary term escapes the frozen source-binding contract."""
    root = Path(root)
    terms = list(terms)
    seen_ids: set[str] = set()
    domain_counts: dict[str, int] = {d.id: 0 for d in GLOSSARY_DOMAINS}

    for entry in terms:
        if not isinstance(entry, GlossaryTerm):
            raise ValueError(f"glossary entry is not a GlossaryTerm: {entry!r}")
        if not _ID_RE.match(entry.id):
            raise ValueError(f"glossary term id is not kebab-case: {entry.id!r}")
        if entry.id in seen_ids:
            raise ValueError(f"duplicate glossary term id: {entry.id!r}")
        seen_ids.add(entry.id)

        if entry.domain not in _DOMAIN_IDS:
            raise ValueError(f"glossary term {entry.id!r}: unknown domain {entry.domain!r}")
        domain_counts[entry.domain] += 1

        for field in ("name_en", "name_zh", "answer_en", "answer_zh"):
            if not getattr(entry, field).strip():
                raise ValueError(f"glossary term {entry.id!r}: {field} is empty")

        if len(entry.answer_en.split()) > 30:
            raise ValueError(f"glossary term {entry.id!r}: answer_en exceeds 30 words")
        if len(entry.answer_zh) > 60:
            raise ValueError(f"glossary term {entry.id!r}: answer_zh exceeds 60 characters")
        if (entry.why_en is None) != (entry.why_zh is None):
            raise ValueError(f"glossary term {entry.id!r}: why_en/why_zh must be both-or-neither")
        if entry.why_en is not None:
            if len(entry.why_en.split()) > 20:
                raise ValueError(f"glossary term {entry.id!r}: why_en exceeds 20 words")
            if len(entry.why_zh) > 40:
                raise ValueError(f"glossary term {entry.id!r}: why_zh exceeds 40 characters")

        for field, text in (
            ("name_en", entry.name_en), ("name_zh", entry.name_zh),
            ("answer_en", entry.answer_en), ("answer_zh", entry.answer_zh),
            ("why_en", entry.why_en or ""), ("why_zh", entry.why_zh or ""),
        ):
            if text:
                _validate_glance_text(entry.id, field, text)

        if not entry.source_file.startswith("docs/site_semantics/") or ".." in entry.source_file:
            raise ValueError(f"glossary term {entry.id!r}: invalid source_file {entry.source_file!r}")
        source_path = Path(entry.source_file)
        if source_path.is_absolute():
            raise ValueError(f"glossary term {entry.id!r}: source_file must be relative")
        full_path = root / source_path
        try:
            lines = full_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"glossary term {entry.id!r}: source file unavailable: {full_path}") from exc
        if entry.source_line < 1 or entry.source_line > len(lines):
            raise ValueError(f"glossary term {entry.id!r}: source_line {entry.source_line} out of range")
        actual = lines[entry.source_line - 1].strip()
        expected_options = (
            f"### {entry.source_heading}",
            f"#### {entry.source_heading}",
            f"## {entry.source_heading}",
        )
        if actual not in expected_options:
            raise ValueError(
                f"glossary term {entry.id!r}: source_line {entry.source_line} does not match heading "
                f"{entry.source_heading!r} in {entry.source_file} (found {actual!r})"
            )

        if not _RELATIVE_HREF_RE.match(entry.page_href):
            raise ValueError(f"glossary term {entry.id!r}: invalid page_href {entry.page_href!r}")

        if not entry.name_en[0].isascii() or not entry.name_en[0].isalpha():
            raise ValueError(f"glossary term {entry.id!r}: name_en must start with an ASCII letter")

    if len(terms) < GLOSSARY_MIN_TERMS:
        raise ValueError(f"glossary defines only {len(terms)} terms; floor is {GLOSSARY_MIN_TERMS}")
    for domain_id, count in domain_counts.items():
        if count < 1:
            raise ValueError(f"glossary domain {domain_id!r} carries no terms")


def glossary_view_model(root: Path, terms: Iterable[GlossaryTerm] = GLOSSARY_TERMS) -> dict:
    """Validate first, then shape the glossary for rendering."""
    root = Path(root)
    terms = list(terms)
    validate_glossary(root, terms)

    domains_out = []
    seen_letters: set[str] = set()
    for domain in GLOSSARY_DOMAINS:
        domain_terms = [t for t in terms if t.domain == domain.id]
        term_rows = []
        for t in domain_terms:
            letter = t.name_en[0].upper()
            is_first = letter not in seen_letters
            if is_first:
                seen_letters.add(letter)
            term_rows.append({
                "id": t.id,
                "name_en": t.name_en,
                "name_zh": t.name_zh,
                "answer_en": t.answer_en,
                "answer_zh": t.answer_zh,
                "why_en": t.why_en,
                "why_zh": t.why_zh,
                "page_href": t.page_href,
                "page_en": t.page_en,
                "page_zh": t.page_zh,
                "letter": letter,
                "letter_anchor": is_first,
                "search": f"{t.name_en.lower()} {t.name_zh} {t.answer_en.lower()} {t.answer_zh}",
            })
        domains_out.append({
            "id": domain.id,
            "label_en": domain.label_en,
            "label_zh": domain.label_zh,
            "count": len(term_rows),
            "terms": term_rows,
        })

    letter_counts: dict[str, int] = {}
    for t in terms:
        letter = t.name_en[0].upper()
        letter_counts[letter] = letter_counts.get(letter, 0) + 1
    letters = [
        {"id": chr(code), "label": chr(code), "count": letter_counts.get(chr(code), 0)}
        for code in range(ord("A"), ord("Z") + 1)
    ]

    return {
        "glossary_state": "complete" if terms else "empty",
        "term_count": len(terms),
        "domains": domains_out,
        "letters": letters,
    }
