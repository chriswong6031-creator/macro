"""Shared view-model contract for first-class international macro dashboards.

The seven-market international engine remains the source of regime, price, FX and
calibrated drawdown-risk facts.  This module turns five of those records into a
uniform, presentation-ready ``international_macro_dashboard.v1`` payload while
keeping regional differences in explicit specs.

Important honesty boundaries:

* ``decision_score`` is a transparent descriptive composite, not a probability.
* ``risk_radar.drawdown_prob`` is the separately calibrated forward measure.
* An unavailable local official series stays unavailable.  A source catalog entry
  never becomes a number merely because the source exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import yaml

from lib import config

SCHEMA = "international_macro_dashboard.v1"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    provider: str
    url: str
    cadence: str
    access: str
    licence: str
    role: str


@dataclass(frozen=True)
class LensSpec:
    key: str
    title_en: str
    title_zh: str
    why_en: str
    why_zh: str
    source_key: str
    metric: str | None = None
    unit: str = ""


@dataclass(frozen=True)
class RegionSpec:
    cc: str
    route: str
    scope_en: str
    scope_zh: str
    central_bank: str
    central_bank_short: str
    index_label: str
    currency_label: str
    action_en: tuple[str, str, str]
    action_zh: tuple[str, str, str]
    transitions_en: tuple[str, str, str]
    transitions_zh: tuple[str, str, str]
    caveat_en: str
    caveat_zh: str
    sources: tuple[SourceSpec, ...]
    lenses: tuple[LensSpec, ...]


def _src(
    key: str,
    provider: str,
    url: str,
    cadence: str,
    access: str,
    licence: str,
    role: str,
) -> SourceSpec:
    return SourceSpec(key, provider, url, cadence, access, licence, role)


COMMON_FRED = _src(
    "fred",
    "Federal Reserve Bank of St. Louis (official-source republisher)",
    "https://fred.stlouisfed.org/",
    "Source dependent",
    "Keyless CSV",
    "FRED terms; underlying series terms retained",
    "Operational fallback for OECD, Eurostat and central-bank series",
)


REGIONS: dict[str, RegionSpec] = {
    "JP": RegionSpec(
        cc="JP",
        route="japan.html",
        scope_en="Japan national economy; Nikkei 225 is market context, not the macro universe.",
        scope_zh="日本全国经济；日经225仅作市场背景，并非宏观统计范围。",
        central_bank="Bank of Japan",
        central_bank_short="BoJ",
        index_label="Nikkei 225",
        currency_label="USD/JPY",
        action_en=(
            "Keep duration and currency risk balanced while growth is soft and inflation pressure persists.",
            "Add cyclical risk only after wages, services inflation and activity confirm a cleaner expansion.",
            "Defend capital: favour quality balance sheets and avoid unhedged yen assumptions.",
        ),
        action_zh=(
            "增长偏软且通胀压力仍在时，均衡久期与汇率风险。",
            "仅在工资、服务通胀与经济活动共同确认更稳健扩张后增加周期风险。",
            "以保本为先：偏好优质资产负债表，避免无对冲日元假设。",
        ),
        transitions_en=(
            "Upgrade: activity and wage breadth turn positive while services inflation remains orderly.",
            "Policy turn: BoJ guidance and the JGB curve reprice together, not on one headline.",
            "Downgrade: yen stress, rising real yields and weaker production fire concurrently.",
        ),
        transitions_zh=(
            "上调：经济活动与工资广度转正，同时服务通胀保持有序。",
            "政策转折：日银指引与JGB曲线同步重定价，而非单一头条。",
            "下调：日元压力、实际收益率上升与工业生产走弱同时触发。",
        ),
        caveat_en="Japan CPI fallback coverage is stale; current inflation detail remains explicitly unavailable until the official adapter is production-verified.",
        caveat_zh="日本CPI备用序列已陈旧；在官方适配器通过生产验证前，当前通胀细项明确显示为不可用。",
        sources=(
            _src(
                "boj",
                "Bank of Japan",
                "https://www.stat-search.boj.or.jp/ssi/mtshtml/m_en.html",
                "Daily / monthly / quarterly",
                "Keyless JSON/CSV API",
                "BOJ statistical-data terms",
                "Policy, Tankan, money, rates and balance of payments",
            ),
            _src(
                "statjp",
                "Statistics Bureau of Japan",
                "https://www.stat.go.jp/english/data/index.html",
                "Monthly / quarterly",
                "Official downloads",
                "Government statistics terms",
                "CPI, labour and household spending",
            ),
            _src(
                "caojp",
                "Cabinet Office, Japan",
                "https://www.esri.cao.go.jp/en/stat/menu.html",
                "Monthly / quarterly",
                "Official downloads",
                "Government statistics terms",
                "GDP, consumption and leading indicators",
            ),
            _src(
                "metijp",
                "Ministry of Economy, Trade and Industry",
                "https://www.meti.go.jp/english/statistics/index.html",
                "Monthly",
                "Official downloads",
                "Government statistics terms",
                "Industrial production and services activity",
            ),
            _src(
                "mofjp",
                "Ministry of Finance, Japan",
                "https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/index.htm",
                "Monthly",
                "Official downloads",
                "Government statistics terms",
                "Trade and external balance",
            ),
            COMMON_FRED,
        ),
        lenses=(
            LensSpec(
                "policy",
                "BoJ normalization",
                "日银政策正常化",
                "Separate a durable policy shift from meeting-day noise.",
                "区分持久政策转变与会议日噪音。",
                "boj",
                "policy_rate",
                "%",
            ),
            LensSpec(
                "wages",
                "Wages & services inflation",
                "工资与服务通胀",
                "The key test of a self-sustaining inflation cycle.",
                "检验通胀周期能否自我维持的核心。",
                "statjp",
            ),
            LensSpec(
                "tankan",
                "Tankan conditions",
                "短观景气",
                "Corporate pricing, capex and labour-intention breadth.",
                "企业定价、资本开支与招聘意向广度。",
                "boj",
            ),
            LensSpec(
                "jgb",
                "JGB curve",
                "日本国债曲线",
                "Transmission channel for normalization and bank duration risk.",
                "政策正常化与银行久期风险的传导渠道。",
                "boj",
                "curve",
                "pp",
            ),
            LensSpec(
                "yen",
                "Yen pressure",
                "日元压力",
                "Imported inflation, funding and foreign-flow pressure.",
                "输入性通胀、融资与外资流动压力。",
                "boj",
                "fx",
                "",
            ),
            LensSpec(
                "production",
                "Production & consumption",
                "生产与消费",
                "Tests whether domestic demand confirms the market tape.",
                "检验内需是否确认市场走势。",
                "metijp",
            ),
            LensSpec(
                "external",
                "Trade & current account",
                "贸易与经常账户",
                "Separates energy-import drag from export competitiveness.",
                "区分能源进口拖累与出口竞争力。",
                "mofjp",
            ),
        ),
    ),
    "KR": RegionSpec(
        cc="KR",
        route="south_korea.html",
        scope_en="Republic of Korea national economy; KOSPI is market context.",
        scope_zh="大韩民国全国经济；KOSPI仅作市场背景。",
        central_bank="Bank of Korea",
        central_bank_short="BOK",
        index_label="KOSPI",
        currency_label="USD/KRW",
        action_en=(
            "Stay balanced while exports and domestic credit send mixed signals.",
            "Add cyclical exposure only when export breadth and domestic demand improve together.",
            "Reduce leverage sensitivity: won stress and household credit can amplify a slowdown.",
        ),
        action_zh=(
            "出口与国内信用信号分化时保持均衡。",
            "仅在出口广度与内需同步改善时增加周期暴露。",
            "降低杠杆敏感度：韩元压力与家庭信贷可放大下行。",
        ),
        transitions_en=(
            "Upgrade: semiconductor/export momentum broadens into domestic demand.",
            "Policy turn: BOK easing arrives without renewed won or housing stress.",
            "Downgrade: exports roll over as household-credit and FX stress rise.",
        ),
        transitions_zh=(
            "上调：半导体/出口动能扩散至内需。",
            "政策转折：韩银宽松且未重新引发韩元或住房压力。",
            "下调：出口回落，同时家庭信贷与汇率压力上升。",
        ),
        caveat_en="BOK ECOS and KOSIS OpenAPI require registered API keys for reliable automation; the live plane uses explicit OECD/FRED fallbacks where configured.",
        caveat_zh="韩银ECOS与KOSIS OpenAPI的可靠自动化需要注册API密钥；当前数据层在已配置处明确使用OECD/FRED备用源。",
        sources=(
            _src(
                "bok",
                "Bank of Korea ECOS",
                "https://ecos.bok.or.kr/",
                "Daily / monthly / quarterly",
                "Registered OpenAPI key",
                "BOK ECOS terms",
                "Policy, money, credit, rates, current account and FX",
            ),
            _src(
                "kosis",
                "KOSIS / Statistics Korea",
                "https://kosis.kr/openapi/index/index.jsp",
                "Monthly / quarterly",
                "Registered OpenAPI key",
                "KOSIS terms",
                "CPI, labour, production, housing and population",
            ),
            _src(
                "motie",
                "Ministry of Trade, Industry and Energy",
                "https://english.motie.go.kr/eng/contents/104",
                "Monthly",
                "Official releases",
                "Government release terms",
                "Exports, imports and industry",
            ),
            COMMON_FRED,
        ),
        lenses=(
            LensSpec(
                "policy",
                "BOK policy",
                "韩银政策",
                "Policy must balance inflation, FX and household leverage.",
                "政策需平衡通胀、汇率与家庭杠杆。",
                "bok",
                "policy_rate",
                "%",
            ),
            LensSpec(
                "exports",
                "Exports & semiconductors",
                "出口与半导体",
                "Korea’s fastest global-demand transmission channel.",
                "韩国最敏感的全球需求传导渠道。",
                "motie",
            ),
            LensSpec(
                "won",
                "Won pressure",
                "韩元压力",
                "A live funding, inflation and foreign-flow stress signal.",
                "融资、通胀与外资流压力的实时信号。",
                "bok",
                "fx",
                "",
            ),
            LensSpec(
                "household",
                "Household credit",
                "家庭信贷",
                "Leverage can mute consumption and constrain policy.",
                "杠杆可抑制消费并约束政策。",
                "bok",
            ),
            LensSpec(
                "housing",
                "Housing pulse",
                "住房脉冲",
                "Collateral and household-balance-sheet transmission.",
                "抵押品与家庭资产负债表传导。",
                "kosis",
            ),
            LensSpec(
                "external",
                "Current account",
                "经常账户",
                "Confirms whether export strength converts into external resilience.",
                "确认出口强势是否转化为外部韧性。",
                "bok",
            ),
        ),
    ),
    "EZ": RegionSpec(
        cc="EZ",
        route="euro_area.html",
        scope_en="Euro area aggregate (current EA21 composition), not the European Union. STOXX Europe 600 is broader market context only.",
        scope_zh="欧元区当前21国总量（EA21），并非欧盟整体。STOXX Europe 600仅作更广泛市场背景。",
        central_bank="European Central Bank",
        central_bank_short="ECB",
        index_label="Euro STOXX / Europe context",
        currency_label="EUR/USD",
        action_en=(
            "Hold balanced risk while disinflation helps but credit transmission remains restrictive.",
            "Add cyclical risk when activity breadth and bank lending turn together.",
            "Protect against fragmentation: watch sovereign spreads, energy and bank credit.",
        ),
        action_zh=(
            "通胀回落提供支持但信贷传导仍偏紧时，保持均衡风险。",
            "经济活动广度与银行贷款同步转强时增加周期风险。",
            "防范碎片化：关注主权利差、能源与银行信贷。",
        ),
        transitions_en=(
            "Upgrade: euro-area growth breadth improves as lending contraction bottoms.",
            "Policy turn: ECB easing transmits into household and business borrowing.",
            "Downgrade: periphery spreads, energy costs and credit stress rise together.",
        ),
        transitions_zh=(
            "上调：欧元区增长广度改善，贷款收缩见底。",
            "政策转折：欧洲央行宽松传导至家庭与企业借贷。",
            "下调：外围利差、能源成本与信贷压力同步上升。",
        ),
        caveat_en="The official unemployment adapter uses current EA21 composition. Legacy EA19/EA20 fallback series remain labelled in provenance until their current-composition official adapters are verified. Broader-Europe equity indexes never substitute for euro-area macro data.",
        caveat_zh="官方失业率适配器采用当前EA21口径。旧EA19/EA20备用序列在当前口径官方适配器验证完成前会在来源中明确标注；更广泛欧洲股票指数绝不替代欧元区宏观数据。",
        sources=(
            _src(
                "ecb",
                "European Central Bank Data Portal",
                "https://data.ecb.europa.eu/help/api/data",
                "Daily / monthly / quarterly",
                "Keyless SDMX API",
                "ECB copyright and reuse policy",
                "Policy, rates, money, credit, bank lending and external balance",
            ),
            _src(
                "eurostat",
                "Eurostat",
                "https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction",
                "Twice-daily API refresh; release dependent",
                "Keyless Statistics and SDMX APIs",
                "European Commission reuse decision",
                "Euro-area HICP, GDP, labour, industry and trade",
            ),
            _src(
                "ec",
                "European Commission",
                "https://economy-finance.ec.europa.eu/economic-forecast-and-surveys/business-and-consumer-surveys_en",
                "Monthly / quarterly",
                "Official downloads",
                "European Commission reuse policy",
                "Business surveys and fiscal context",
            ),
            COMMON_FRED,
        ),
        lenses=(
            LensSpec(
                "policy",
                "ECB transmission",
                "欧洲央行传导",
                "The rate path matters only if financing conditions follow.",
                "只有融资条件跟随，利率路径才有意义。",
                "ecb",
                "policy_rate",
                "%",
            ),
            LensSpec(
                "hicp",
                "HICP core/services",
                "核心/服务HICP",
                "Tests whether disinflation is broad enough for durable easing.",
                "检验通胀回落是否足够广泛以支持持续宽松。",
                "eurostat",
                "cpi_yoy",
                "% y/y",
            ),
            LensSpec(
                "credit",
                "Bank lending & credit",
                "银行贷款与信贷",
                "The euro area’s dominant private-sector transmission channel.",
                "欧元区私人部门的主要传导渠道。",
                "ecb",
            ),
            LensSpec(
                "spreads",
                "Sovereign spreads",
                "主权利差",
                "Fragmentation risk can tighten conditions unevenly.",
                "碎片化风险可导致各国金融条件不均衡收紧。",
                "ecb",
            ),
            LensSpec(
                "energy",
                "Energy sensitivity",
                "能源敏感度",
                "Separates imported cost shocks from domestic inflation.",
                "区分输入性成本冲击与国内通胀。",
                "eurostat",
            ),
            LensSpec(
                "external",
                "External balance",
                "外部平衡",
                "Tracks competitiveness and imported-energy drag.",
                "追踪竞争力与能源进口拖累。",
                "ecb",
            ),
        ),
    ),
    "GB": RegionSpec(
        cc="GB",
        route="united_kingdom.html",
        scope_en="United Kingdom national economy; FTSE 100 and FTSE 250 are market context.",
        scope_zh="英国全国经济；富时100与富时250仅作市场背景。",
        central_bank="Bank of England",
        central_bank_short="BoE",
        index_label="FTSE 100 / FTSE 250",
        currency_label="GBP/USD",
        action_en=(
            "Stay selective while sticky services inflation offsets improving growth.",
            "Add domestic cyclicals when real wages, housing and credit improve without reflation.",
            "Cut rate-sensitive risk if gilt, mortgage and sterling stress reinforce each other.",
        ),
        action_zh=(
            "服务通胀黏性抵消增长改善时保持精选。",
            "实际工资、住房与信贷改善且未再通胀时增加国内周期风险。",
            "若国债、按揭与英镑压力相互强化，降低利率敏感风险。",
        ),
        transitions_en=(
            "Upgrade: real-wage gains broaden into consumption and housing stabilization.",
            "Policy turn: services inflation and wage growth cool enough for durable BoE easing.",
            "Downgrade: gilt yields and mortgage resets tighten into weaker labour demand.",
        ),
        transitions_zh=(
            "上调：实际工资增长扩散至消费与住房企稳。",
            "政策转折：服务通胀与工资增速降温，支持持续降息。",
            "下调：国债收益率与按揭重定价收紧，并传导至劳动力需求走弱。",
        ),
        caveat_en="ONS labour-market estimates carry survey-response and methodology uncertainty; the dashboard treats labour as one input, not a standalone trigger.",
        caveat_zh="ONS劳动力市场估计受调查回复率与方法变化影响；本看板将就业视为一项输入，而非独立触发器。",
        sources=(
            _src(
                "boe",
                "Bank of England",
                "https://www.bankofengland.co.uk/boeapps/database/",
                "Daily / monthly",
                "Official IADB downloads",
                "BoE terms of use",
                "Policy, SONIA, gilt curve, money, credit and mortgages",
            ),
            _src(
                "ons",
                "Office for National Statistics",
                "https://developer.ons.gov.uk/",
                "Release dependent",
                "Keyless v1 beta API",
                "Open Government Licence",
                "CPI, wages, labour, GDP, production, trade and housing",
            ),
            _src(
                "obr",
                "Office for Budget Responsibility",
                "https://obr.uk/data/",
                "Forecast-event dependent",
                "Official downloads",
                "Open Government Licence",
                "Fiscal context and forecast assumptions",
            ),
            COMMON_FRED,
        ),
        lenses=(
            LensSpec(
                "policy",
                "BoE policy",
                "英央行政策",
                "Services inflation and wages dominate the reaction function.",
                "服务通胀与工资主导政策反应函数。",
                "boe",
                "policy_rate",
                "%",
            ),
            LensSpec(
                "services",
                "Services inflation",
                "服务通胀",
                "The clearest domestic persistence test.",
                "最清晰的国内通胀黏性检验。",
                "ons",
                "cpi_yoy",
                "% y/y",
            ),
            LensSpec(
                "wages",
                "Wage growth",
                "工资增长",
                "Real-income support versus persistence risk.",
                "实际收入支持与通胀黏性风险的平衡。",
                "ons",
            ),
            LensSpec(
                "gilts",
                "Gilt curve",
                "英国国债曲线",
                "Links policy, fiscal risk and mortgage pricing.",
                "连接货币政策、财政风险与按揭定价。",
                "boe",
                "curve",
                "pp",
            ),
            LensSpec(
                "housing",
                "Housing & mortgages",
                "住房与按揭",
                "A high-frequency household cash-flow transmission channel.",
                "家庭现金流的高频传导渠道。",
                "boe",
            ),
            LensSpec(
                "fiscal",
                "Fiscal context",
                "财政背景",
                "Supply, taxes and issuance can alter the rate path.",
                "供给、税收与发债可改变利率路径。",
                "obr",
            ),
            LensSpec(
                "sterling",
                "Sterling",
                "英镑",
                "Imported inflation and cross-border confidence signal.",
                "输入性通胀与跨境信心信号。",
                "boe",
                "fx",
                "",
            ),
        ),
    ),
    "IN": RegionSpec(
        cc="IN",
        route="india.html",
        scope_en="India national economy; Nifty 50 and Sensex are market context.",
        scope_zh="印度全国经济；Nifty 50与Sensex仅作市场背景。",
        central_bank="Reserve Bank of India",
        central_bank_short="RBI",
        index_label="Nifty 50 / Sensex",
        currency_label="USD/INR",
        action_en=(
            "Keep growth exposure balanced against food inflation, liquidity and rupee risk.",
            "Add cyclicals when industrial activity, credit quality and rural demand broaden together.",
            "Reduce leverage if food inflation, liquidity tightness and rupee pressure become concurrent.",
        ),
        action_zh=(
            "在增长暴露与食品通胀、流动性及卢比风险之间保持平衡。",
            "工业活动、信贷质量与农村需求同步扩散时增加周期风险。",
            "若食品通胀、流动性收紧与卢比压力同时出现，降低杠杆。",
        ),
        transitions_en=(
            "Upgrade: IIP, private credit and consumption broaden beyond public capex.",
            "Policy turn: food inflation cools enough for RBI easing without rupee stress.",
            "Downgrade: monsoon/food shock, tighter liquidity and weaker external balance coincide.",
        ),
        transitions_zh=(
            "上调：工业生产、私人信贷与消费扩散至公共资本开支之外。",
            "政策转折：食品通胀降温，支持RBI宽松且不引发卢比压力。",
            "下调：季风/食品冲击、流动性收紧与外部平衡走弱同时出现。",
        ),
        caveat_en="India’s official data are distributed across MoSPI and RBI systems. Until each adapter passes release-period and unit checks, unavailable fields remain blank rather than backfilled with unrelated proxies.",
        caveat_zh="印度官方数据分布于MoSPI与RBI系统。在各适配器通过发布期与单位检查前，不可用字段保持空白，不以无关代理补填。",
        sources=(
            _src(
                "mospi",
                "Ministry of Statistics and Programme Implementation",
                "https://api.mospi.gov.in/",
                "Monthly / quarterly",
                "Official CPI API and eSankhyiki client",
                "Government data terms",
                "CPI, IIP, GDP and labour",
            ),
            _src(
                "rbi",
                "Reserve Bank of India DBIE",
                "https://data.rbi.org.in/DBIE/",
                "Daily / weekly / monthly",
                "Official downloads",
                "RBI database terms",
                "Policy, liquidity, credit, rates, reserves and external balance",
            ),
            _src(
                "commercein",
                "Ministry of Commerce and Industry",
                "https://tradestat.commerce.gov.in/",
                "Monthly",
                "Official downloads",
                "Government data terms",
                "Merchandise trade and WPI context",
            ),
            _src(
                "imd",
                "India Meteorological Department",
                "https://mausam.imd.gov.in/",
                "Daily / seasonal",
                "Official bulletins",
                "Government data terms",
                "Monsoon timing and rainfall",
            ),
            COMMON_FRED,
        ),
        lenses=(
            LensSpec(
                "policy",
                "RBI policy & liquidity",
                "RBI政策与流动性",
                "The stance is the rate plus banking-system liquidity.",
                "政策立场由利率与银行体系流动性共同决定。",
                "rbi",
                "policy_rate",
                "%",
            ),
            LensSpec(
                "food",
                "Food inflation",
                "食品通胀",
                "The main volatility channel into household purchasing power.",
                "影响家庭购买力的主要波动渠道。",
                "mospi",
                "cpi_yoy",
                "% y/y",
            ),
            LensSpec(
                "wpi",
                "WPI pipeline",
                "WPI价格链",
                "Tracks input-cost pressure before consumer pass-through.",
                "追踪传导至消费者前的投入成本压力。",
                "commercein",
            ),
            LensSpec(
                "monsoon",
                "Monsoon sensitivity",
                "季风敏感度",
                "Affects food supply, rural income and inflation tails.",
                "影响食品供给、农村收入与通胀尾部。",
                "imd",
            ),
            LensSpec(
                "iip",
                "Industrial production",
                "工业生产",
                "Tests whether capex and manufacturing breadth are durable.",
                "检验资本开支与制造业广度是否持久。",
                "mospi",
            ),
            LensSpec(
                "credit",
                "Credit & liquidity",
                "信贷与流动性",
                "Separates healthy expansion from funding pressure.",
                "区分健康扩张与融资压力。",
                "rbi",
            ),
            LensSpec(
                "external",
                "Rupee, reserves & external balance",
                "卢比、储备与外部平衡",
                "The buffer against oil and global-funding shocks.",
                "抵御油价与全球融资冲击的缓冲。",
                "rbi",
                "fx",
                "",
            ),
            LensSpec(
                "fiscal",
                "Fiscal capex",
                "财政资本开支",
                "Distinguishes public-investment impulse from private breadth.",
                "区分公共投资脉冲与私人部门广度。",
                "mospi",
            ),
        ),
    ),
}

ROUTES = {cc: spec.route for cc, spec in REGIONS.items()}

METRIC_LABELS: dict[str, tuple[str, str, str]] = {
    "cpi_yoy": ("Inflation", "通胀", "% y/y"),
    "gdp_yoy": ("Real growth", "实际增长", "% y/y"),
    "unemployment": ("Unemployment", "失业率", "%"),
    "yield_10y": ("10-year yield", "10年期收益率", "%"),
    "policy_rate": ("Policy / short rate", "政策/短端利率", "%"),
    "curve": ("10y minus short rate", "10年期减短端", "pp"),
    "fx": ("FX reference", "汇率参考", ""),
    "fx_strength_3m": ("Currency strength, 3m", "货币强弱，3个月", "%"),
    "drawdown": ("Index from 52w high", "指数距52周高点", "%"),
    "realvol": ("Realized volatility", "实现波动率", "%"),
}


def _finite(value: Any) -> float | None:
    try:
        value = float(value)
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def _score_parts(
    growth: Any,
    inflation: Any,
    recession: Any,
    liquidity: str | None,
    risk_state: str | None = None,
) -> dict[str, float]:
    """Return transparent descriptive score components.

    The macro history can reproduce the first four terms.  The current score adds
    a small, separately labelled risk-radar state adjustment.
    """
    growth_v = _finite(growth) or 0.0
    inflation_v = _finite(inflation) or 0.0
    recession_v = _finite(recession)
    liquidity_adj = {"expanding": 5.0, "contracting": -5.0}.get(str(liquidity), 0.0)
    risk_adj = {"risk": -8.0, "caution": -4.0, "clear": 2.0}.get(str(risk_state), 0.0)
    return {
        "base": 50.0,
        "growth": round(growth_v * 22.0, 2),
        "inflation": round(-max(inflation_v, 0.0) * 10.0, 2),
        "recession": round(-(recession_v or 0.0) * 0.18, 2),
        "liquidity": liquidity_adj,
        "risk_state": risk_adj,
    }


def decision_score(record: dict[str, Any]) -> tuple[int, dict[str, float]]:
    radar = record.get("risk_radar") or {}
    parts = _score_parts(
        record.get("growth_score"),
        record.get("inflation_score"),
        record.get("recession_score"),
        record.get("liquidity"),
        radar.get("state"),
    )
    return round(max(0.0, min(100.0, sum(parts.values())))), parts


def _score_state(score: int) -> tuple[str, str, str]:
    if score >= 64:
        return "constructive", "Constructive", "积极"
    if score >= 45:
        return "balanced", "Balanced", "均衡"
    return "defensive", "Defensive", "防御"


def _spark(history: pd.DataFrame | None) -> dict[str, Any]:
    if history is None or history.empty:
        return {"values": [], "points": "", "min": None, "max": None}
    d = history.tail(60).copy()
    values: list[int] = []
    dates: list[str] = []
    for idx, row in d.iterrows():
        parts = _score_parts(
            row.get("growth_score"),
            row.get("inflation_score"),
            row.get("recession_score"),
            row.get("liquidity"),
        )
        values.append(round(max(0.0, min(100.0, sum(parts.values())))))
        dates.append(str(pd.Timestamp(idx).date()))
    if len(values) == 1:
        points = "0,50 100,50"
    else:
        points = " ".join(
            f"{i * 100 / (len(values) - 1):.2f},{100 - v:.2f}"
            for i, v in enumerate(values)
        )
    return {
        "values": values,
        "dates": dates,
        "points": points,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
    }


def _parse_period(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    try:
        text = str(raw)
        if len(text) == 7:
            text += "-01"
        elif len(text) == 4:
            text += "-01-01"
        return datetime.fromisoformat(text[:10]).date()
    except (TypeError, ValueError):
        return None


def _health(metric: str, asof: Any, today: date) -> dict[str, Any]:
    parsed = _parse_period(asof)
    if parsed is None:
        return {"metric": metric, "asof": None, "age_days": None, "state": "missing"}
    age = max(0, (today - parsed).days)
    threshold = 160 if metric == "gdp" else 80
    return {
        "metric": metric,
        "asof": str(asof),
        "age_days": age,
        "state": "fresh" if age <= threshold else "stale",
    }


def _format_value(value: Any, unit: str) -> str:
    v = _finite(value)
    if v is None:
        return "Unavailable"
    if abs(v) >= 100:
        text = f"{v:,.2f}"
    else:
        text = f"{v:.2f}"
    return f"{text}{unit}" if unit else text


def _events(spec: RegionSpec, today: date) -> list[dict[str, Any]]:
    path = config.data_dir() / "intl_risk" / "cb_calendar.yml"
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    out: list[dict[str, Any]] = []
    for bank_key, bank in (raw.get("banks") or {}).items():
        if bank.get("country") not in {spec.cc, "XM" if spec.cc == "EZ" else spec.cc}:
            continue
        for raw_date in bank.get("dates") or []:
            event_date = _parse_period(raw_date)
            if event_date is None:
                continue
            if event_date < today:
                state, outcome = (
                    "released",
                    "Decision date passed — verify the official release",
                )
            elif event_date == today:
                state, outcome = "today", "Decision due today"
            else:
                state, outcome = "upcoming", "Scheduled — no outcome yet"
            out.append(
                {
                    "date": event_date.isoformat(),
                    "bank": bank_key,
                    "name_en": bank.get("name_en", bank_key),
                    "name_zh": bank.get("name_zh", bank_key),
                    "state": state,
                    "outcome_en": outcome,
                    "outcome_zh": {
                        "released": "决议日期已过——请核对官方发布",
                        "today": "决议今日公布",
                        "upcoming": "已排期——尚无结果",
                    }[state],
                    "source": bank.get("source"),
                }
            )
    out.sort(key=lambda item: item["date"])
    past = [item for item in out if item["state"] == "released"][-2:]
    current = [item for item in out if item["state"] != "released"][:5]
    return past + current


def build_country_view(
    record: dict[str, Any],
    history: pd.DataFrame | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    cc = str(record.get("cc") or "")
    if cc not in REGIONS:
        raise KeyError(f"unsupported international macro dashboard: {cc}")
    spec = REGIONS[cc]
    today = today or datetime.now(timezone.utc).date()
    score, parts = decision_score(record)
    state_key, state_en, state_zh = _score_state(score)
    state_index = {"constructive": 1, "balanced": 0, "defensive": 2}[state_key]
    macro = record.get("macro") or {}
    macro_asof = record.get("macro_asof") or {}
    radar = record.get("risk_radar") or {}
    drawdown_prob = radar.get("drawdown_prob") or {}

    metrics = []
    for key in (
        "cpi_yoy",
        "gdp_yoy",
        "unemployment",
        "yield_10y",
        "policy_rate",
        "curve",
        "fx",
        "fx_strength_3m",
        "drawdown",
        "realvol",
    ):
        en, zh, unit = METRIC_LABELS[key]
        raw = macro.get(key)
        metrics.append(
            {
                "key": key,
                "label_en": en,
                "label_zh": zh,
                "raw": _finite(raw),
                "value": _format_value(raw, unit),
                "unit": unit,
                "asof": macro_asof.get("gdp" if key == "gdp_yoy" else key),
            }
        )

    source_by_key = {source.key: source for source in spec.sources}
    lenses = []
    for lens in spec.lenses:
        source = source_by_key[lens.source_key]
        raw_value = macro.get(lens.metric) if lens.metric else None
        lenses.append(
            {
                "key": lens.key,
                "title_en": lens.title_en,
                "title_zh": lens.title_zh,
                "why_en": lens.why_en,
                "why_zh": lens.why_zh,
                "value": _format_value(raw_value, lens.unit)
                if lens.metric
                else "Awaiting verified official adapter",
                "available": _finite(raw_value) is not None if lens.metric else False,
                "metric": lens.metric,
                "source_key": source.key,
                "source": source.provider,
                "source_url": source.url,
            }
        )

    health = []
    for metric in ("cpi_yoy", "gdp", "unemployment", "yield_10y"):
        item = _health(metric, macro_asof.get(metric), today)
        item["label_en"] = {
            "cpi_yoy": "Inflation",
            "gdp": "Growth",
            "unemployment": "Labour",
            "yield_10y": "Rates",
        }[metric]
        item["label_zh"] = {
            "cpi_yoy": "通胀",
            "gdp": "增长",
            "unemployment": "就业",
            "yield_10y": "利率",
        }[metric]
        health.append(item)

    source_rows = []
    for source in spec.sources:
        is_fallback = source.key == "fred"
        source_rows.append(
            {
                "key": source.key,
                "provider": source.provider,
                "url": source.url,
                "cadence": source.cadence,
                "access": source.access,
                "licence": source.licence,
                "role": source.role,
                "status": "active fallback"
                if is_fallback
                else "authoritative target / active where mapped",
            }
        )

    return {
        "schema": SCHEMA,
        "route": spec.route,
        "cc": cc,
        # The comparative engine's legacy label is "Eurozone"; the first-class
        # route uses the official/product scope name "Euro Area".
        "name": "Euro Area" if cc == "EZ" else record.get("name"),
        "name_zh": "欧元区" if cc == "EZ" else record.get("name_zh"),
        "flag": record.get("flag"),
        "scope_en": spec.scope_en,
        "scope_zh": spec.scope_zh,
        "asof": record.get("date"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "regime": {
            "quad": record.get("quad"),
            "name": record.get("quad_name"),
            "growth_score": record.get("growth_score"),
            "inflation_score": record.get("inflation_score"),
            "confidence": record.get("confidence"),
            "liquidity": record.get("liquidity"),
            "recession_score": record.get("recession_score"),
            "recession_band": record.get("recession_band"),
            "data_limited": bool(record.get("data_limited")),
        },
        "decision": {
            "score": score,
            "state": state_key,
            "state_en": state_en,
            "state_zh": state_zh,
            "action_en": spec.action_en[state_index],
            "action_zh": spec.action_zh[state_index],
            "transitions_en": spec.transitions_en,
            "transitions_zh": spec.transitions_zh,
            "parts": parts,
            "method_en": "50 + growth impulse − inflation pressure − recession stress + liquidity + current calibrated-risk state. Descriptive, not a forecast.",
            "method_zh": "50 + 增长脉冲 − 通胀压力 − 衰退压力 + 流动性 + 当前校准风险状态。仅作描述，不是预测。",
        },
        "history": _spark(history),
        "market": {
            "index_label": spec.index_label,
            "currency_label": spec.currency_label,
            "equity": record.get("equity") or {},
        },
        "policy": {
            "bank": spec.central_bank,
            "short": spec.central_bank_short,
            "rate": _finite(macro.get("policy_rate")),
            "curve": _finite(macro.get("curve")),
        },
        "risk": {
            "state": radar.get("state"),
            "top_score": radar.get("top_score"),
            "dominant_en": radar.get("dominant_label_en"),
            "dominant_zh": radar.get("dominant_label_zh"),
            "h21": _finite(drawdown_prob.get("h21")),
            "measure": drawdown_prob.get("measure"),
            "trajectory": radar.get("trajectory") or {},
            "scares": radar.get("scares") or [],
            "calibrated": _finite(drawdown_prob.get("h21")) is not None,
        },
        "metrics": metrics,
        "lenses": lenses,
        "events": _events(spec, today),
        "health": health,
        "sources": source_rows,
        "caveat_en": spec.caveat_en,
        "caveat_zh": spec.caveat_zh,
        "navigation": [
            {
                "cc": other.cc,
                "name": REGIONS[other.cc]
                .route.replace(".html", "")
                .replace("_", " ")
                .title(),
                "route": other.route,
                "active": other.cc == cc,
            }
            for other in REGIONS.values()
        ],
    }


def load_history(cc: str) -> pd.DataFrame | None:
    path = config.data_dir() / "intl_regime" / f"{cc}_history.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001 — a missing parquet engine/history degrades the chart
        return None


def validate_view(view: dict[str, Any]) -> None:
    """Small runtime contract check used by the builder and tests."""
    if view.get("schema") != SCHEMA:
        raise ValueError("unexpected international macro dashboard schema")
    if view.get("cc") not in REGIONS:
        raise ValueError("unknown country code")
    score = (view.get("decision") or {}).get("score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("decision score must be an integer in [0, 100]")
    if not view.get("metrics") or not view.get("sources") or not view.get("lenses"):
        raise ValueError("dashboard view is missing required evidence planes")


def source_catalog() -> dict[str, list[dict[str, str]]]:
    """Serializable source registry for documentation/health tooling."""
    return {
        cc: [
            {
                "key": source.key,
                "provider": source.provider,
                "url": source.url,
                "cadence": source.cadence,
                "access": source.access,
                "licence": source.licence,
                "role": source.role,
            }
            for source in spec.sources
        ]
        for cc, spec in REGIONS.items()
    }
