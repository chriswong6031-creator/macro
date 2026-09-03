from __future__ import annotations

from collections import Counter
import importlib
import importlib.util
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
STRATEGY_PATH = REPO / "config" / "linear_initiative_portfolio.v1.json"

EXPECTED_INITIATIVES = {
    "canonical-intelligence-substrate-learning": ("Canonical Intelligence Substrate & Learning", 2),
    "legendary-alpha-discovery-timing": ("Legendary Alpha Discovery & Timing", 1),
    "institutional-company-event-intelligence": ("Institutional Company & Event Intelligence", 2),
    "global-markets-regimes-risk-command": ("Global Markets, Regimes & Risk Command", 2),
    "personal-institutional-desk": ("Personal Institutional Desk", 1),
    "trusted-production-customer-platform": ("Trusted Production & Customer Platform", 2),
    "autonomous-ai-organization": ("Autonomous AI Organization", 1),
}

EXPECTED_MEMBERSHIPS = {
    "WS:ALPHA-INTELLIGENCE-INTEGRATION": "canonical-intelligence-substrate-learning",
    "WS:GMI-THEME-GRAPH": "canonical-intelligence-substrate-learning",
    "WS:STOCK-IDENTITY": "canonical-intelligence-substrate-learning",
    "WS:MARKET-MEMORY-W2C": "canonical-intelligence-substrate-learning",
    "WS:MASSIVE-STOCK-DAY-R2-COHERENCE": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-MEASUREMENT-LAW": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-EVIDENCE-VIEW": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-T1-ENGINE-REGISTRY": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-OUTPUT-HEALTH": "canonical-intelligence-substrate-learning",
    "WS:ADVANCED-DATA-OPTIONS": "legendary-alpha-discovery-timing",
    "WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY": "legendary-alpha-discovery-timing",
    "WS:INTRADAY-FLOW-P0-RECOVERY": "legendary-alpha-discovery-timing",
    "WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2": "legendary-alpha-discovery-timing",
    "WS:CHINA-ALPHA-INTELLIGENCE": "legendary-alpha-discovery-timing",
    "WS:CN-LIMIT-ALPHA": "legendary-alpha-discovery-timing",
    "WS:PROPHET-CONDITIONAL-FUSION": "legendary-alpha-discovery-timing",
    "WS:PROPHET-HK-CA-REVAMP": "legendary-alpha-discovery-timing",
    "WS:PROPHET-US-AVAILABILITY": "legendary-alpha-discovery-timing",
    "WS:PROPHET-US-ENTRY-TIMING": "legendary-alpha-discovery-timing",
    "WS:PROPHET-US-V4-RECOVERY": "legendary-alpha-discovery-timing",
    "WS:LIVE-ENTRY-RADAR": "legendary-alpha-discovery-timing",
    "WS:BREATHING-PLATFORM": "legendary-alpha-discovery-timing",
    "WS:TOP-ANATOMY": "legendary-alpha-discovery-timing",
    "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER": "institutional-company-event-intelligence",
    "WS:FINANCIAL-INTELLIGENCE-FABRIC": "institutional-company-event-intelligence",
    "WS:CALCBENCH-FILING-FORENSICS-PARITY": "institutional-company-event-intelligence",
    "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2": "institutional-company-event-intelligence",
    "WS:DEFENSE-PROCUREMENT-V3": "institutional-company-event-intelligence",
    "WS:BPC-JV-RECON": "institutional-company-event-intelligence",
    "WS:CN-SOE-DEMAND": "institutional-company-event-intelligence",
    "WS:BIOCATALYST-CORE-PRODUCT": "institutional-company-event-intelligence",
    "WS:BIOCATALYST-RECOVERY-V2": "institutional-company-event-intelligence",
    "WS:EARNINGS-INTELLIGENCE-OS": "institutional-company-event-intelligence",
    "WS:FUNDAMENTAL-FORENSICS": "institutional-company-event-intelligence",
    "WS:RATES-INFLATION-COMMAND": "global-markets-regimes-risk-command",
    "WS:MACRO-CONTEXT-INDEX": "global-markets-regimes-risk-command",
    "WS:GREY-DEER-RISK-INTELLIGENCE": "global-markets-regimes-risk-command",
    "WS:CRYPTO-INTELLIGENCE": "global-markets-regimes-risk-command",
    "WS:CYCLE-PATTERN-ISSUER-MECHANISM": "global-markets-regimes-risk-command",
    "WS:MARKET-OS": "personal-institutional-desk",
    "WS:STOCK-DOSSIER-LIVE-QUOTE": "personal-institutional-desk",
    "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2": "personal-institutional-desk",
    "WS:ACCOUNT-IDENTITY-HARDENING": "trusted-production-customer-platform",
    "WS:CUSTOMER-DATA-BACKUP": "trusted-production-customer-platform",
    "WS:COMMERCIAL-PATH-ALERTING": "trusted-production-customer-platform",
    "WS:CI-MERGE-CONTROL-PLANE": "trusted-production-customer-platform",
    "WS:RUNNER-FLEET-RESILIENCE": "trusted-production-customer-platform",
    "WS:AGENT-OS": "autonomous-ai-organization",
    "WS:CHAIRMAN-CONTROL-ROOM": "autonomous-ai-organization",
    "WS:EXECUTIVE-CAPACITY-FABRIC": "autonomous-ai-organization",
}

EXPECTED_EXCEPTIONS = {
    ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
    ("linear_project_id", "9aef6461-306a-4a3c-911b-c6a4b6635a78", "canonical_parent_unresolved"),
}


def _lip():
    spec = importlib.util.find_spec("scripts.linear_initiative_plan")
    assert spec is not None, "Task 1 RED: scripts.linear_initiative_plan is not implemented yet"
    return importlib.import_module("scripts.linear_initiative_plan")


def _project_plan(*, active_keys=(), excluded_keys=()):
    return {
        "schema": "linear_portfolio_plan.v1",
        "active_projects": [{"workstream_key": key} for key in active_keys],
        "review_candidates": [],
        "excluded_projects": [{"workstream_key": key} for key in excluded_keys],
    }


def test_strategy_file_has_frozen_v1_shape():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    assert strategy["schema"] == lip.STRATEGY_SCHEMA
    assert set(strategy["initiatives"]) == set(EXPECTED_INITIATIVES)
    for key, (name, priority) in EXPECTED_INITIATIVES.items():
        row = strategy["initiatives"][key]
        assert row["name"] == name
        assert row["priority"] == priority
        assert row["status"] == "Active"
        assert row["lead_team"] == "MastermindX"
        assert row["owner"] is None
        assert row["target_date"] is None
        assert row["health"] is None
        assert row["labels"] == []
        assert row["parent_initiatives"] == []
        assert row["summary"]
        assert row["outcome"]
        assert row["moat"]
        assert row["completion_ruler"]
        assert row["scope_law"]

    assert strategy["memberships"] == EXPECTED_MEMBERSHIPS
    exceptions = {
        (row["identity_kind"], row["identity"], row["reason"])
        for row in strategy["unassigned_exceptions"]
    }
    assert exceptions == EXPECTED_EXCEPTIONS

    counts = Counter(strategy["memberships"].values())
    assert counts == {
        "canonical-intelligence-substrate-learning": 9,
        "legendary-alpha-discovery-timing": 14,
        "institutional-company-event-intelligence": 11,
        "global-markets-regimes-risk-command": 5,
        "personal-institutional-desk": 3,
        "trusted-production-customer-platform": 5,
        "autonomous-ai-organization": 3,
    }
    assert len(strategy["memberships"]) == 50
    assert "WS:WATCHLIST-PORTFOLIO-CEO" not in strategy["memberships"]


def test_validate_strategy_accepts_exact_current_universe_shape():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    active = sorted(
        set(EXPECTED_MEMBERSHIPS)
        - {
            "WS:EVAL-OS-T1-ENGINE-REGISTRY",
            "WS:EVAL-OS-OUTPUT-HEALTH",
            "WS:BIOCATALYST-CORE-PRODUCT",
            "WS:BIOCATALYST-RECOVERY-V2",
            "WS:EARNINGS-INTELLIGENCE-OS",
            "WS:FUNDAMENTAL-FORENSICS",
            "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2",
        }
        | {"WS:WATCHLIST-PORTFOLIO-CEO"}
    )
    excluded = sorted(set(EXPECTED_MEMBERSHIPS) - set(active))
    lip.validate_strategy(strategy, _project_plan(active_keys=active, excluded_keys=excluded))


def test_validate_strategy_refuses_unmapped_active_workstream():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(strategy, _project_plan(active_keys=["WS:NEW-ACTIVE"]))
    assert "strategy_unmapped_active_workstream" in {row["code"] for row in exc.value.failures}


def test_validate_strategy_refuses_exception_that_is_also_mapped():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    mutated = {**strategy, "memberships": {**strategy["memberships"], "WS:WATCHLIST-PORTFOLIO-CEO": "personal-institutional-desk"}}
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(mutated, _project_plan(active_keys=["WS:WATCHLIST-PORTFOLIO-CEO"]))
    assert "strategy_exception_also_mapped" in {row["code"] for row in exc.value.failures}


def test_validate_strategy_refuses_unknown_initiative_key():
    lip = _lip()
    strategy = lip.load_strategy(STRATEGY_PATH)
    mutated = {**strategy, "memberships": {**strategy["memberships"], "WS:MARKET-OS": "not-a-real-initiative"}}
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(mutated, _project_plan(active_keys=["WS:MARKET-OS"]))
    assert "strategy_unknown_initiative_key" in {row["code"] for row in exc.value.failures}
