"""Current-epoch Linear Initiative contract tests.

Imported by ``tests/test_agentos_compile.py`` so the existing Agent OS/self-mod
CI lane executes the 7/62/2 contract without adding another workflow or job.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts import linear_initiative_plan as lip
from scripts import linear_portfolio_plan as lpp

REPO = Path(__file__).resolve().parents[1]
STRATEGY = REPO / "config" / "linear_initiative_portfolio.v1.json"
EXPECTED_SOURCE = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "path": (
        "docs/superpowers/specs/"
        "2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md"
    ),
    "protected_revision": "84d74cf9c7b81ba70169ab7df1f71835da2d297b",
}
EXPECTED_GROUP_COUNTS = {
    "autonomous-ai-organization": 7,
    "canonical-intelligence-substrate-learning": 10,
    "global-markets-regimes-risk-command": 6,
    "institutional-company-event-intelligence": 11,
    "legendary-alpha-discovery-timing": 16,
    "personal-institutional-desk": 4,
    "trusted-production-customer-platform": 8,
}
REQUIRED_CURRENT = {
    "WS:AGENT-EVAL-FABRIC": "autonomous-ai-organization",
    "WS:CODE-INTELLIGENCE-FABRIC": "autonomous-ai-organization",
    "WS:CROSS-REPO-CONTRACT-GOVERNANCE": "canonical-intelligence-substrate-learning",
    "WS:EXECUTIVE-ATTENTION-ECONOMICS": "autonomous-ai-organization",
    "WS:EXECUTIVE-OS-DISASTER-RECOVERY": "trusted-production-customer-platform",
    "WS:FLOW-OBSERVATORY-V2": "global-markets-regimes-risk-command",
    "WS:OPERATION-ASSURANCE": "autonomous-ai-organization",
    "WS:PROPHET-CANDIDATE-ADDED-DATE": "legendary-alpha-discovery-timing",
    "WS:REACTIVE-PROJECTION": "personal-institutional-desk",
    "WS:REPRODUCIBLE-WORKER-ENVIRONMENTS": "trusted-production-customer-platform",
    "WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE": "legendary-alpha-discovery-timing",
    "WS:TERMINAL-GITHUB-CANONICALIZATION": "trusted-production-customer-platform",
}
PARKED_ALIAS = "WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT"


def _strategy() -> dict:
    return json.loads(STRATEGY.read_text(encoding="utf-8"))


def _row(key: str, *, status: str = "active") -> dict:
    return {
        "workstream_key": key,
        "desired_project_name": f"{key} — projected",
        "desired_project_status_class": "completed" if status == "done" else "active",
        "canonical_status": status,
    }


def _project_plan(strategy: dict | None = None) -> dict:
    strategy = strategy or _strategy()
    rows = [_row(key) for key in sorted(strategy["memberships"])]
    rows.append(_row("WS:WATCHLIST-PORTFOLIO-CEO"))
    return {
        "schema": lpp.PLAN_SCHEMA,
        "semantic_hash": "linear-project-plan-current-epoch",
        "active_projects": rows,
        "review_candidates": [],
        "excluded_projects": [],
    }


def _codes(error: lip.InitiativePlanError) -> set[str]:
    return {row["code"] for row in error.failures}


def test_linear_initiative_strategy_is_exact_workspace_level_7_62_2() -> None:
    strategy = _strategy()
    assert strategy["schema"] == lip.STRATEGY_SCHEMA
    assert strategy["source_design"] == EXPECTED_SOURCE
    assert len(strategy["initiatives"]) == 7
    assert len(strategy["memberships"]) == 62
    assert len(strategy["unassigned_exceptions"]) == 2
    assert dict(sorted(Counter(strategy["memberships"].values()).items())) == (
        EXPECTED_GROUP_COUNTS
    )
    assert {key: strategy["memberships"][key] for key in REQUIRED_CURRENT} == (
        REQUIRED_CURRENT
    )
    assert PARKED_ALIAS not in strategy["memberships"]
    for initiative in strategy["initiatives"].values():
        assert initiative["status"] == "Active"
        assert initiative["lead_team"] is None
        assert initiative["owner"] is None
        assert initiative["target_date"] is None
        assert initiative["health"] is None
        assert initiative["labels"] == []
        assert initiative["parent_initiatives"] == []
    lip.validate_strategy(strategy, _project_plan(strategy))


@pytest.mark.parametrize(
    "revision",
    [
        "d004f5bf7953e943281dff7efd8fe17a54b0cf6c",
        "043d0c52ccd82edc11521c90c85dfd8d1b678a3e",
        "0000000000000000000000000000000000000000",
    ],
)
def test_superseded_source_epoch_is_rejected(revision: str) -> None:
    strategy = _strategy()
    strategy["source_design"]["protected_revision"] = revision
    with pytest.raises(lip.InitiativePlanError) as caught:
        lip.validate_strategy(strategy, _project_plan())
    assert "strategy_source_design_invalid" in _codes(caught.value)


def test_missing_current_membership_and_group_drift_fail_closed() -> None:
    strategy = _strategy()
    strategy["memberships"].pop("WS:CODE-INTELLIGENCE-FABRIC")
    with pytest.raises(lip.InitiativePlanError) as caught:
        lip.validate_strategy(strategy, _project_plan())
    assert {
        "strategy_membership_count_mismatch",
        "strategy_current_membership_mismatch",
        "strategy_group_counts_mismatch",
    } <= _codes(caught.value)


def test_parked_terminal_alias_cannot_replace_canonical_identity() -> None:
    strategy = _strategy()
    initiative = strategy["memberships"].pop("WS:TERMINAL-GITHUB-CANONICALIZATION")
    strategy["memberships"][PARKED_ALIAS] = initiative
    with pytest.raises(lip.InitiativePlanError) as caught:
        lip.validate_strategy(strategy, _project_plan(strategy))
    assert {
        "strategy_parked_workstream_mapped",
        "strategy_current_membership_mismatch",
    } <= _codes(caught.value)


def test_new_unclassified_active_workstream_fails_closed() -> None:
    strategy = _strategy()
    project_plan = _project_plan(strategy)
    project_plan["active_projects"].append(_row("WS:UNCLASSIFIED-FUTURE"))
    with pytest.raises(lip.InitiativePlanError) as caught:
        lip.validate_strategy(strategy, project_plan)
    assert "strategy_unmapped_active_workstream" in _codes(caught.value)


def test_current_plan_and_receipt_are_deterministic_and_hash_bound() -> None:
    strategy = _strategy()
    project_plan = _project_plan(strategy)
    first, first_receipt = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=STRATEGY,
    )
    second, second_receipt = lip.compile_initiative_plan(
        project_plan=copy.deepcopy(project_plan),
        strategy_path=STRATEGY,
    )
    assert lpp.semantic_json(first) == lpp.semantic_json(second)
    assert first_receipt == second_receipt
    assert first["summary"]["desired_initiatives"] == 7
    assert first["summary"]["desired_memberships"] == 62
    assert first["summary"]["unassigned_exceptions"] == 2
    assert first["summary"]["group_counts"] == EXPECTED_GROUP_COUNTS
    assert first_receipt["strategy_content_sha256"]
    assert first_receipt["desired_memberships_sha256"]
