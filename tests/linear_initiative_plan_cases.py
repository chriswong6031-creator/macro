from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts import linear_initiative_plan as lip

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
EXPECTED_COUNTS = {
    "canonical-intelligence-substrate-learning": 9,
    "legendary-alpha-discovery-timing": 14,
    "institutional-company-event-intelligence": 11,
    "global-markets-regimes-risk-command": 5,
    "personal-institutional-desk": 3,
    "trusted-production-customer-platform": 5,
    "autonomous-ai-organization": 3,
}
EXPECTED_EXCEPTIONS = {
    ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
    ("linear_project_id", "9aef6461-306a-4a3c-911b-c6a4b6635a78", "canonical_parent_unresolved"),
}


def _membership_rows(strategy):
    return [
        (workstream_key, initiative_key)
        for initiative_key, workstream_keys in strategy["memberships"].items()
        for workstream_key in workstream_keys
    ]


def _project_plan_for(strategy):
    mapped = sorted({key for key, _ in _membership_rows(strategy)})
    return {
        "active_projects": [
            {"workstream_key": key}
            for key in mapped + ["WS:WATCHLIST-PORTFOLIO-CEO"]
        ],
        "review_candidates": [],
        "excluded_projects": [],
    }


def _failure_codes(exc):
    return {row["code"] for row in exc.value.failures}


def test_frozen_v1_strategy_shape_and_memberships():
    strategy = lip.load_strategy(STRATEGY_PATH)
    initiatives = {row["key"]: row for row in strategy["initiatives"]}

    assert {
        key: (row["name"], row["priority"])
        for key, row in initiatives.items()
    } == EXPECTED_INITIATIVES

    for row in initiatives.values():
        assert row["status"] == "Active"
        assert row["lead_team"] == "MastermindX"
        assert row["owner"] is None
        assert row["target_date"] is None
        assert row["health"] is None
        assert row["labels"] == []
        assert row["parent_initiatives"] == []
        for prose_field in ("summary", "outcome", "moat", "completion_ruler", "scope_law"):
            assert isinstance(row[prose_field], str) and row[prose_field].strip()

    rows = _membership_rows(strategy)
    assert len(rows) == 50
    assert Counter(initiative for _, initiative in rows) == Counter(EXPECTED_COUNTS)
    assert all(key.startswith("WS:") for key, _ in rows)
    assert len({key for key, _ in rows}) == 50
    assert "WS:WATCHLIST-PORTFOLIO-CEO" not in {key for key, _ in rows}

    assert {
        (row["binding"], row["value"], row["reason"])
        for row in strategy["unassigned_exceptions"]
    } == EXPECTED_EXCEPTIONS


def test_exact_strategy_validates_against_exact_project_universe():
    strategy = lip.load_strategy(STRATEGY_PATH)
    lip.validate_strategy(strategy, _project_plan_for(strategy))


def test_wrong_schema_is_a_typed_refusal(tmp_path):
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.load_strategy(path)
    assert _failure_codes(exc) == {"strategy_wrong_schema"}


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda doc: doc["initiatives"].pop(), "strategy_initiative_count_mismatch"),
        (lambda doc: doc["initiatives"].append(copy.deepcopy(doc["initiatives"][0])), "strategy_duplicate_initiative_key"),
        (lambda doc: doc["initiatives"].__setitem__(1, {**doc["initiatives"][1], "name": doc["initiatives"][0]["name"]}), "strategy_duplicate_initiative_name"),
        (lambda doc: doc["initiatives"][0].__setitem__("status", "Planned"), "strategy_initiative_field_mismatch"),
        (lambda doc: doc["memberships"]["canonical-intelligence-substrate-learning"].pop(), "strategy_membership_count_mismatch"),
        (lambda doc: doc["memberships"]["legendary-alpha-discovery-timing"].append(doc["memberships"]["canonical-intelligence-substrate-learning"][0]), "strategy_duplicate_membership"),
        (lambda doc: doc["memberships"].__setitem__("unknown-initiative", [doc["memberships"]["canonical-intelligence-substrate-learning"][0]]), "strategy_unknown_initiative_key"),
        (lambda doc: doc["unassigned_exceptions"].pop(), "strategy_exception_mismatch"),
        (lambda doc: doc["memberships"]["personal-institutional-desk"].append("WS:WATCHLIST-PORTFOLIO-CEO"), "strategy_exception_also_mapped"),
    ],
)
def test_strategy_mutations_fail_closed(mutator, expected_code):
    strategy = lip.load_strategy(STRATEGY_PATH)
    mutated = copy.deepcopy(strategy)
    mutator(mutated)
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(mutated, _project_plan_for(strategy))
    assert expected_code in _failure_codes(exc)


def test_unknown_membership_and_unmapped_active_workstream_fail_closed():
    strategy = lip.load_strategy(STRATEGY_PATH)
    plan = _project_plan_for(strategy)

    unknown = copy.deepcopy(strategy)
    unknown["memberships"]["personal-institutional-desk"].append("WS:NOT-CANONICAL")
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(unknown, plan)
    assert "strategy_membership_unknown_workstream" in _failure_codes(exc)

    plan["active_projects"].append({"workstream_key": "WS:NEW-ACTIVE"})
    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(strategy, plan)
    assert "strategy_unmapped_active_workstream" in _failure_codes(exc)
