"""Closed registry of Macro & Monetary workspace identities (F01).

The twelve workspace ids are frozen by the architecture (section 7.2). Only ids
in :data:`WORKSPACE_IDS` may appear in a snapshot; the schema enforces the same
set. R1A implements exactly one entry (``liquidity_regime`` / US). The other
eleven are declared here as ``NOT_BUILT`` placeholders so the registry is a
single, honest source of truth for the suite — a workspace does not become
"registered as live" merely by appearing in this list.
"""
from __future__ import annotations

from typing import Mapping

# The closed, ordered set of the twelve workspace identities (architecture 7.2).
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
}

# Declare the remaining eleven so the registry lists the whole suite honestly.
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
