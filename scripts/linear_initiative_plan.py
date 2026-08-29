#!/usr/bin/env python3
"""Deterministic strategy validation for the Linear Initiative portfolio v1."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts import linear_portfolio_plan as lpp

STRATEGY_SCHEMA = "linear_initiative_portfolio_strategy.v1"
PLAN_SCHEMA = "linear_initiative_plan.v1"
RECEIPT_SCHEMA = "linear_initiative_plan_receipt.v1"
SNAPSHOT_SCHEMA = "linear_initiative_snapshot.v1"
PROJECT_PLAN_SCHEMA = lpp.PLAN_SCHEMA

_EXPECTED_INITIATIVE_COUNT = 7
_EXPECTED_MEMBERSHIP_COUNT = 50
_EXPECTED_EXCEPTIONS = {
    ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
    ("linear_project_id", "9aef6461-306a-4a3c-911b-c6a4b6635a78", "canonical_parent_unresolved"),
}
_REQUIRED_PROSE_FIELDS = ("name", "summary", "outcome", "moat", "completion_ruler", "scope_law")
_EXPECTED_STATIC_FIELDS = {
    "status": "Active",
    "lead_team": "MastermindX",
    "owner": None,
    "target_date": None,
    "health": None,
    "labels": [],
    "parent_initiatives": [],
}


class InitiativePlanError(RuntimeError):
    """Deterministic, machine-readable refusal for invalid Initiative strategy."""

    def __init__(self, failures: Sequence[Mapping[str, Any]]) -> None:
        self.failures = tuple(dict(row) for row in failures)
        super().__init__(f"linear initiative plan refused: {len(self.failures)} hard defect(s)")


def load_strategy(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InitiativePlanError(
            [{"code": "strategy_unreadable", "error": type(exc).__name__}]
        ) from exc
    if not isinstance(doc, dict) or doc.get("schema") != STRATEGY_SCHEMA:
        raise InitiativePlanError([{"code": "strategy_wrong_schema"}])
    return doc


def _project_keys(project_plan: Mapping[str, Any], bucket: str) -> set[str]:
    rows = project_plan.get(bucket)
    if not isinstance(rows, list):
        return set()
    return {
        row["workstream_key"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("workstream_key"), str)
        and row["workstream_key"].startswith("WS:")
    }


def _exception_rows(strategy: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    rows = strategy.get("unassigned_exceptions")
    if not isinstance(rows, list):
        return set()
    return {
        (row.get("binding"), row.get("value"), row.get("reason"))
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("binding"), str)
        and isinstance(row.get("value"), str)
        and isinstance(row.get("reason"), str)
    }


def validate_strategy(
    strategy: Mapping[str, Any], project_plan: Mapping[str, Any]
) -> None:
    failures: list[dict[str, Any]] = []
    initiatives = strategy.get("initiatives")
    if not isinstance(initiatives, list):
        initiatives = []
    if len(initiatives) != _EXPECTED_INITIATIVE_COUNT:
        failures.append(
            {
                "code": "strategy_initiative_count_mismatch",
                "current": len(initiatives),
                "expected": _EXPECTED_INITIATIVE_COUNT,
            }
        )

    initiative_keys = [row.get("key") for row in initiatives if isinstance(row, dict)]
    initiative_names = [row.get("name") for row in initiatives if isinstance(row, dict)]
    duplicate_keys = sorted(
        key for key, count in Counter(initiative_keys).items() if isinstance(key, str) and count > 1
    )
    duplicate_names = sorted(
        name for name, count in Counter(initiative_names).items() if isinstance(name, str) and count > 1
    )
    if duplicate_keys:
        failures.append({"code": "strategy_duplicate_initiative_key", "keys": duplicate_keys})
    if duplicate_names:
        failures.append({"code": "strategy_duplicate_initiative_name", "names": duplicate_names})

    for index, row in enumerate(initiatives):
        if not isinstance(row, dict):
            failures.append(
                {"code": "strategy_initiative_field_mismatch", "index": index, "field": "row"}
            )
            continue
        for field, expected in _EXPECTED_STATIC_FIELDS.items():
            if row.get(field) != expected:
                failures.append(
                    {
                        "code": "strategy_initiative_field_mismatch",
                        "initiative_key": row.get("key"),
                        "field": field,
                        "current": row.get(field),
                        "expected": expected,
                    }
                )
        if row.get("priority") not in {1, 2}:
            failures.append(
                {
                    "code": "strategy_initiative_field_mismatch",
                    "initiative_key": row.get("key"),
                    "field": "priority",
                }
            )
        if not isinstance(row.get("key"), str) or not row.get("key"):
            failures.append(
                {"code": "strategy_initiative_field_mismatch", "index": index, "field": "key"}
            )
        for field in _REQUIRED_PROSE_FIELDS:
            if not isinstance(row.get(field), str) or not row[field].strip():
                failures.append(
                    {
                        "code": "strategy_initiative_field_mismatch",
                        "initiative_key": row.get("key"),
                        "field": field,
                    }
                )

    valid_initiative_keys = {key for key in initiative_keys if isinstance(key, str)}
    memberships = strategy.get("memberships")
    if not isinstance(memberships, dict):
        memberships = {}
    unknown_groups = sorted(set(memberships) - valid_initiative_keys)
    if unknown_groups:
        failures.append({"code": "strategy_unknown_initiative_key", "keys": unknown_groups})

    membership_rows: list[tuple[str, str]] = []
    for initiative_key, workstream_keys in memberships.items():
        if not isinstance(workstream_keys, list):
            failures.append(
                {
                    "code": "strategy_initiative_field_mismatch",
                    "initiative_key": initiative_key,
                    "field": "memberships",
                }
            )
            continue
        membership_rows.extend(
            (workstream_key, initiative_key)
            for workstream_key in workstream_keys
            if isinstance(workstream_key, str)
        )
    if len(membership_rows) != _EXPECTED_MEMBERSHIP_COUNT:
        failures.append(
            {
                "code": "strategy_membership_count_mismatch",
                "current": len(membership_rows),
                "expected": _EXPECTED_MEMBERSHIP_COUNT,
            }
        )
    membership_counts = Counter(key for key, _ in membership_rows)
    duplicate_memberships = sorted(key for key, count in membership_counts.items() if count > 1)
    if duplicate_memberships:
        failures.append(
            {"code": "strategy_duplicate_membership", "workstream_keys": duplicate_memberships}
        )

    exceptions = _exception_rows(strategy)
    if exceptions != _EXPECTED_EXCEPTIONS:
        failures.append(
            {
                "code": "strategy_exception_mismatch",
                "current": sorted(exceptions),
                "expected": sorted(_EXPECTED_EXCEPTIONS),
            }
        )
    mapped_keys = set(membership_counts)
    mapped_exception_keys = sorted(
        value
        for binding, value, _ in _EXPECTED_EXCEPTIONS
        if binding == "workstream_key" and value in mapped_keys
    )
    if mapped_exception_keys:
        failures.append(
            {
                "code": "strategy_exception_also_mapped",
                "workstream_keys": mapped_exception_keys,
            }
        )

    active_keys = _project_keys(project_plan, "active_projects")
    universe = (
        active_keys
        | _project_keys(project_plan, "review_candidates")
        | _project_keys(project_plan, "excluded_projects")
    )
    unknown_memberships = sorted(mapped_keys - universe)
    if unknown_memberships:
        failures.append(
            {
                "code": "strategy_membership_unknown_workstream",
                "workstream_keys": unknown_memberships,
            }
        )

    allowed_unmapped_active = {
        value
        for binding, value, _ in _EXPECTED_EXCEPTIONS
        if binding == "workstream_key"
    }
    unmapped_active = sorted(active_keys - mapped_keys - allowed_unmapped_active)
    if unmapped_active:
        failures.append(
            {
                "code": "strategy_unmapped_active_workstream",
                "workstream_keys": unmapped_active,
            }
        )

    if failures:
        raise InitiativePlanError(failures)
