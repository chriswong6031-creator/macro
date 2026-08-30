#!/usr/bin/env python3
"""Deterministic validation for the Chairman-approved Linear Initiative strategy.

This Task-1 module is deliberately zero-network and write-free. Project lifecycle
selection remains owned by ``scripts.linear_portfolio_plan``; this module only
validates the static strategic classification layered above its emitted plan.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts import linear_portfolio_plan as lpp  # noqa: E402

STRATEGY_SCHEMA = "linear_initiative_portfolio_strategy.v1"
PLAN_SCHEMA = "linear_initiative_plan.v1"
RECEIPT_SCHEMA = "linear_initiative_plan_receipt.v1"
SNAPSHOT_SCHEMA = "linear_initiative_snapshot.v1"

_EXPECTED_INITIATIVES = {
    "canonical-intelligence-substrate-learning": ("Canonical Intelligence Substrate & Learning", 2),
    "legendary-alpha-discovery-timing": ("Legendary Alpha Discovery & Timing", 1),
    "institutional-company-event-intelligence": ("Institutional Company & Event Intelligence", 2),
    "global-markets-regimes-risk-command": ("Global Markets, Regimes & Risk Command", 2),
    "personal-institutional-desk": ("Personal Institutional Desk", 1),
    "trusted-production-customer-platform": ("Trusted Production & Customer Platform", 2),
    "autonomous-ai-organization": ("Autonomous AI Organization", 1),
}
_EXPECTED_INITIATIVE_FIELDS = {
    "status": "Active",
    "lead_team": "MastermindX",
    "owner": None,
    "target_date": None,
    "health": None,
    "labels": [],
    "parent_initiatives": [],
}
_REQUIRED_PROSE_FIELDS = ("summary", "outcome", "moat", "completion_ruler", "scope_law")
_EXPECTED_EXCEPTIONS = {
    ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
    ("linear_project_id", "9aef6461-306a-4a3c-911b-c6a4b6635a78", "canonical_parent_unresolved"),
}
_WATCHLIST_EXCEPTION = "WS:WATCHLIST-PORTFOLIO-CEO"


class InitiativePlanError(RuntimeError):
    """Deterministic machine-readable refusal for a strategic-plan defect."""

    def __init__(self, failures: Sequence[Mapping[str, Any]]) -> None:
        self.failures = tuple(dict(row) for row in failures)
        super().__init__(f"linear initiative plan refused: {len(self.failures)} hard defect(s)")


def load_strategy(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != STRATEGY_SCHEMA:
        raise InitiativePlanError([{"code": "strategy_wrong_schema"}])
    return doc


def _project_keys(project_plan: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    if project_plan.get("schema") != lpp.PLAN_SCHEMA:
        raise InitiativePlanError([{"code": "project_plan_wrong_schema"}])
    universe: set[str] = set()
    active: set[str] = set()
    for field in ("active_projects", "review_candidates", "excluded_projects"):
        rows = project_plan.get(field, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            key = row.get("workstream_key")
            if isinstance(key, str) and key.startswith("WS:"):
                universe.add(key)
                if field in {"active_projects", "review_candidates"}:
                    active.add(key)
    return universe, active


def _membership_mapping(raw: Any, failures: list[dict[str, Any]]) -> dict[str, str]:
    if isinstance(raw, Mapping):
        return {
            str(key): str(value)
            for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    if isinstance(raw, list):
        out: dict[str, str] = {}
        seen: set[str] = set()
        for row in raw:
            if not isinstance(row, Mapping):
                continue
            key = row.get("workstream_key")
            initiative = row.get("initiative_key")
            if not isinstance(key, str) or not isinstance(initiative, str):
                continue
            if key in seen:
                failures.append({"code": "strategy_duplicate_membership", "workstream_key": key})
            seen.add(key)
            out[key] = initiative
        return out
    return {}


def _initiative_mapping(raw: Any, failures: list[dict[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if isinstance(raw, Mapping):
        return {
            str(key): value
            for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, Mapping)
        }
    if isinstance(raw, list):
        out: dict[str, Mapping[str, Any]] = {}
        seen: set[str] = set()
        for row in raw:
            if not isinstance(row, Mapping) or not isinstance(row.get("key"), str):
                continue
            key = row["key"]
            if key in seen:
                failures.append({"code": "strategy_duplicate_initiative_key", "initiative_key": key})
            seen.add(key)
            out[key] = row
        return out
    return {}


def validate_strategy(strategy: Mapping[str, Any], project_plan: Mapping[str, Any]) -> None:
    failures: list[dict[str, Any]] = []
    if strategy.get("schema") != STRATEGY_SCHEMA:
        failures.append({"code": "strategy_wrong_schema"})

    initiatives = _initiative_mapping(strategy.get("initiatives"), failures)
    if len(initiatives) != len(_EXPECTED_INITIATIVES):
        failures.append({
            "code": "strategy_initiative_count_mismatch",
            "expected": len(_EXPECTED_INITIATIVES),
            "actual": len(initiatives),
        })

    names: dict[str, str] = {}
    for key, row in initiatives.items():
        name = row.get("name")
        if isinstance(name, str):
            if name in names:
                failures.append({
                    "code": "strategy_duplicate_initiative_name",
                    "initiative_name": name,
                    "initiative_keys": sorted({names[name], key}),
                })
            else:
                names[name] = key

        expected = _EXPECTED_INITIATIVES.get(key)
        mismatched: list[str] = []
        if expected is None:
            mismatched.append("key")
        else:
            expected_name, expected_priority = expected
            if row.get("name") != expected_name:
                mismatched.append("name")
            if row.get("priority") != expected_priority:
                mismatched.append("priority")
        for field, value in _EXPECTED_INITIATIVE_FIELDS.items():
            if row.get(field) != value:
                mismatched.append(field)
        for field in _REQUIRED_PROSE_FIELDS:
            if not isinstance(row.get(field), str) or not row[field].strip():
                mismatched.append(field)
        if mismatched:
            failures.append({
                "code": "strategy_initiative_field_mismatch",
                "initiative_key": key,
                "fields": sorted(set(mismatched)),
            })

    memberships = _membership_mapping(strategy.get("memberships"), failures)
    if len(memberships) != 50:
        failures.append({"code": "strategy_membership_count_mismatch", "expected": 50, "actual": len(memberships)})

    initiative_keys = set(_EXPECTED_INITIATIVES)
    for workstream_key, initiative_key in memberships.items():
        if initiative_key not in initiative_keys:
            failures.append({
                "code": "strategy_unknown_initiative_key",
                "workstream_key": workstream_key,
                "initiative_key": initiative_key,
            })

    raw_exceptions = strategy.get("unassigned_exceptions")
    exception_rows = raw_exceptions if isinstance(raw_exceptions, list) else []
    exception_set = {
        (row.get("identity_kind"), row.get("identity"), row.get("reason"))
        for row in exception_rows
        if isinstance(row, Mapping)
    }
    if exception_set != _EXPECTED_EXCEPTIONS:
        failures.append({
            "code": "strategy_exception_mismatch",
            "expected": sorted(_EXPECTED_EXCEPTIONS),
            "actual": sorted(exception_set, key=lambda row: tuple(str(item) for item in row)),
        })

    for identity_kind, identity, _reason in exception_set:
        if identity_kind == "workstream_key" and isinstance(identity, str) and identity in memberships:
            failures.append({"code": "strategy_exception_also_mapped", "workstream_key": identity})

    universe, active = _project_keys(project_plan)
    for workstream_key in sorted(memberships):
        if workstream_key not in universe:
            failures.append({"code": "strategy_membership_unknown_workstream", "workstream_key": workstream_key})

    for workstream_key in sorted(active):
        if workstream_key not in memberships and workstream_key != _WATCHLIST_EXCEPTION:
            failures.append({"code": "strategy_unmapped_active_workstream", "workstream_key": workstream_key})

    if failures:
        raise InitiativePlanError(failures)
