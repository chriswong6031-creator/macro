"""Closed registry of Macro & Monetary workspace identities.

The twelve F01 workspace ids are frozen by the architecture (section 7.2);
expansion ids (Chairman-authorized 2026-09-04) append after them and never
interleave. Only ids in :data:`WORKSPACE_IDS` may appear in a snapshot; the
schema's ``$defs.workspaceId`` enum enforces the same set (cross-pinned by
tests/test_macro_workspace_contract.py). Any id without an explicit ``BUILT``
entry below is declared as a ``NOT_BUILT`` placeholder so the registry is a
single, honest source of truth for the suite — a workspace does not become
"registered as live" merely by appearing in this list.
"""
from __future__ import annotations

from typing import Mapping

# The closed, ordered set of workspace identities: the frozen F01 twelve
# (architecture 7.2) followed by appended expansion ids.
WORKSPACE_IDS: tuple[str, ...] = (
    "liquidity_regime",
    "growth_real_economy",
    "capital_structure",
    "business_activity",
    "labor_markets",
    "inflation_system",
    "monetary_policy",
    "financial_conditions",
    "liquidity_central_banks",
    "housing_real_estate",
    "consumer_payments",
    "national_debt_liabilities",
    # Beyond-F01 expansion (Chairman-authorized 2026-09-04): the closed F01 set
    # is the twelve above; expansion ids are appended, never interleaved.
    "rates_curves",
)

# Build state of the *dedicated workspace* (never the substrate).
_NOT_BUILT = "NOT_BUILT"
_BUILT = "BUILT"

REGISTRY: dict[str, dict] = {
    "liquidity_regime": {
        "id": "liquidity_regime",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.liquidity_regime",
        "method_version": "liquidity_regime.compose.v1",
        "title_en": "Liquidity Regime Monitor",
        "title_zh": "流动性体制监测",
        "subtitle_en": "Funding pressure x balance-sheet support",
        "subtitle_zh": "融资压力 × 资产负债表支持",
        # Components whose absence/staleness degrades the whole page (conservative
        # freshness is taken over this set). Optional refinements are excluded.
        "required_components": (
            "net_liquidity_roc",
            "liquidity_quality_level",
            "nfci_pctile",
            "ofr_fsi_pctile",
        ),
    },
    "growth_real_economy": {
        "id": "growth_real_economy",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.growth",
        "method_version": "growth_real_economy.compose.v1",
        "title_en": "Growth & Real Economy",
        "title_zh": "增长与实体经济",
        "subtitle_en": "Growth momentum x level/breadth",
        "subtitle_zh": "增长动能 × 水平/广度",
        "required_components": (
            "gdpnow_growth",
            "wei_growth",
            "leading_diffusion",
            "coincident_diffusion",
        ),
    },
    "business_activity": {
        "id": "business_activity",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.business_activity",
        "method_version": "business_activity.compose.v1",
        "title_en": "Business Activity",
        "title_zh": "商业活动",
        "subtitle_en": "Cycle tiers: leading x coincident x lagging",
        "subtitle_zh": "周期分层：领先 × 同步 × 滞后",
        "required_components": ("leading_tier", "coincident_tier"),
    },
    "labor_markets": {
        "id": "labor_markets",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.labor",
        "method_version": "labor_markets.compose.v1",
        "title_en": "Labor Markets",
        "title_zh": "劳动力市场",
        "subtitle_en": "Labor demand x labor supply/tightness",
        "subtitle_zh": "劳动力需求 × 劳动力供给/紧张度",
        "required_components": (
            "claims_momentum",
            "job_postings_momentum",
            "sahm_rule_level",
            "claims_recession_subscore",
        ),
    },
    "inflation_system": {
        "id": "inflation_system",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.inflation",
        "method_version": "inflation_system.compose.v1",
        "title_en": "Inflation System",
        "title_zh": "通胀体系",
        "subtitle_en": "Inflation impulse x persistence & breadth",
        "subtitle_zh": "通胀冲量 × 持续性与广度",
        "required_components": (
            "core_cpi_annualized_3m",
            "headline_cpi_annualized_3m",
            "sticky_flexible_spread",
            "core_acceleration_3m_minus_6m",
        ),
    },
    "monetary_policy": {
        "id": "monetary_policy",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.monetary_policy",
        "method_version": "monetary_policy.compose.v1",
        "title_en": "Monetary Policy",
        "title_zh": "货币政策",
        "subtitle_en": "Policy stance x market-implied path",
        "subtitle_zh": "政策立场 × 市场隐含路径",
        "required_components": (
            "fed_funds_rate",
            "market_implied_path_12m",
            "curve_2s10s",
            "fed_balance_sheet_impulse",
        ),
    },
    "financial_conditions": {
        "id": "financial_conditions",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.financial_conditions",
        "method_version": "financial_conditions.compose.v1",
        "title_en": "Financial Conditions",
        "title_zh": "金融条件",
        "subtitle_en": "Conditions level x impulse",
        "subtitle_zh": "条件水平 × 边际冲量",
        "required_components": (
            "nfci_pctile",
            "ofr_fsi_pctile",
            "hy_oas_pct",
            "real_10y_pctile",
            "vol_regime_risk_score",
        ),
    },
    "liquidity_central_banks": {
        "id": "liquidity_central_banks",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.liquidity_central_banks",
        "method_version": "liquidity_central_banks.compose.v1",
        "title_en": "Liquidity & Central Banks",
        "title_zh": "流动性与央行",
        "subtitle_en": "Global monetary impulse x Fed/ECB/BoJ balance-sheet stance",
        "subtitle_zh": "全球货币脉冲 × 美联储/欧央行/日央行资产负债表姿态",
        "required_components": (
            "glt_monetary_impulse",
            "glt_liquidity_breadth",
            "glt_usd_funding_impulse",
            "cb_fed_balance_sheet_impulse_13w",
        ),
    },
    "capital_structure": {
        "id": "capital_structure",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.capital_structure",
        "method_version": "capital_structure.compose.v1",
        "title_en": "Capital Structure",
        "title_zh": "资本结构",
        "subtitle_en": "Refinancing pressure x balance-sheet resilience/market access",
        "subtitle_zh": "再融资压力 × 资产负债表韧性/市场准入",
        "required_components": ("event_coverage_census", "issuer_records"),
    },
    "housing_real_estate": {
        "id": "housing_real_estate",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.housing",
        "method_version": "housing_real_estate.compose.v1",
        "title_en": "Housing & Real Estate",
        "title_zh": "住房与房地产",
        "subtitle_en": "Demand/transaction momentum x affordability/financing pressure",
        "subtitle_zh": "需求/成交动能 × 可负担性/融资压力",
        "required_components": (
            "mortgage_rate",
            "housing_starts",
            "building_permits",
            "case_shiller_hpi",
        ),
    },
    "consumer_payments": {
        "id": "consumer_payments",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.consumer_payments",
        "method_version": "consumer_payments.compose.v1",
        "title_en": "Consumer & Payments",
        "title_zh": "消费与支付",
        "subtitle_en": "Cash-flow/spending momentum x consumer credit stress",
        "subtitle_zh": "现金流/支出动能 × 消费信贷压力",
        # Only the two series populated on disk today are required; the seven
        # config-appended consumer_household legs are optional until the nightly
        # collect lands them (housing's ZORI precedent — optional never degrades).
        "required_components": (
            "retail_sales",
            "consumer_sentiment",
        ),
    },
    "national_debt_liabilities": {
        "id": "national_debt_liabilities",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.national_debt",
        "method_version": "national_debt_liabilities.compose.v1",
        "title_en": "National Debt & Liabilities",
        "title_zh": "国债与负债",
        "subtitle_en": "Refinancing/issuance pressure x fiscal capacity/interest-burden resilience",
        "subtitle_zh": "再融资/发行压力 × 财政能力/利息负担韧性",
        "required_components": (
            "tga",
            "net_issuance",
            "withheld_taxes",
            "auction_demand",
        ),
    },
    "rates_curves": {
        "id": "rates_curves",
        "build_state": _BUILT,
        "regions_supported": ("US",),
        "producer": "engine.market_os.macro_workspaces.rates_curves",
        "method_version": "rates_curves.compose.v1",
        "title_en": "Rates & Curves",
        "title_zh": "利率与曲线",
        "subtitle_en": "The Treasury curve node by node",
        "subtitle_zh": "逐点解读美债收益率曲线",
        "required_components": (
            "us3m",
            "us6m",
            "us2y",
            "us5y",
            "us10y",
            "us30y",
            "us5y_real",
            "us10y_real",
            "breakeven_10y",
            "breakeven_5y5y",
            "term_premium_10y",
            "effr",
            "sofr",
            "iorb",
        ),
    },
}

# Declare the remaining not-yet-built workspaces so the registry lists the
# whole suite honestly (R2 built the six MCS/cycle producers above).
for _wid in WORKSPACE_IDS:
    REGISTRY.setdefault(
        _wid,
        {
            "id": _wid,
            "build_state": _NOT_BUILT,
            "regions_supported": (),
            "producer": None,
            "method_version": None,
        },
    )


def is_known(workspace_id: str) -> bool:
    return workspace_id in WORKSPACE_IDS


def entry(workspace_id: str) -> Mapping:
    if workspace_id not in REGISTRY:
        raise KeyError(f"unknown workspace id: {workspace_id!r}")
    return REGISTRY[workspace_id]


def built_ids() -> tuple[str, ...]:
    return tuple(w for w in WORKSPACE_IDS if REGISTRY[w]["build_state"] == _BUILT)


def all_ids() -> tuple[str, ...]:
    return WORKSPACE_IDS
