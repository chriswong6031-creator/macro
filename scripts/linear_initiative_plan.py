#!/usr/bin/env python3
"""Deterministic Linear Initiative desired-state and drift compiler.

Project lifecycle selection remains owned by ``scripts.linear_portfolio_plan``.
This module layers the Chairman-approved strategic Initiative classification
over that Project plan. It performs zero network calls and zero Linear writes.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
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
_HARD_DRIFT_CODES = frozenset({
    "unexpected_initiative",
    "initiative_name_ambiguous",
    "initiative_id_ambiguous",
    "project_binding_ambiguous",
    "project_id_ambiguous",
    "membership_multi_parent",
    "membership_initiative_id_unknown",
    "membership_duplicate_initiative_id",
    "membership_identity_conflict",
    "exception_has_forbidden_membership",
    "unmapped_visible_project",
})


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
    if len(memberships) != 52:
        failures.append({
            "code": "strategy_membership_count_mismatch",
            "expected": 52,
            "actual": len(memberships),
        })

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
            "actual": sorted(
                exception_set,
                key=lambda row: tuple(str(item) for item in row),
            ),
        })

    for identity_kind, identity, _reason in exception_set:
        if (
            identity_kind == "workstream_key"
            and isinstance(identity, str)
            and identity in memberships
        ):
            failures.append({
                "code": "strategy_exception_also_mapped",
                "workstream_key": identity,
            })

    universe, active = _project_keys(project_plan)
    for workstream_key in sorted(memberships):
        if workstream_key not in universe:
            failures.append({
                "code": "strategy_membership_unknown_workstream",
                "workstream_key": workstream_key,
            })

    for workstream_key in sorted(active):
        if workstream_key not in memberships and workstream_key != _WATCHLIST_EXCEPTION:
            failures.append({
                "code": "strategy_unmapped_active_workstream",
                "workstream_key": workstream_key,
            })

    if failures:
        raise InitiativePlanError(failures)


def render_description(row: Mapping[str, Any]) -> str:
    """Render approved Initiative prose without adding new semantics."""
    return (
        f"Outcome: {row['outcome']}\n\n"
        f"Moat: {row['moat']}\n\n"
        f"Completion ruler: {row['completion_ruler']}\n\n"
        f"Scope law: {row['scope_law']}"
    )


def _load_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InitiativePlanError([{
            "code": "initiative_snapshot_unreadable",
            "path": str(path),
            "error": type(exc).__name__,
        }]) from exc
    if not isinstance(doc, dict) or doc.get("schema") != SNAPSHOT_SCHEMA:
        raise InitiativePlanError([{
            "code": "initiative_snapshot_wrong_schema",
            "path": str(path),
        }])
    return doc


def _project_rows(
    project_plan: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    rows: dict[str, Mapping[str, Any]] = {}
    active: set[str] = set()
    for bucket in ("active_projects", "review_candidates", "excluded_projects"):
        raw_rows = project_plan.get(bucket, [])
        if not isinstance(raw_rows, list):
            continue
        for row in raw_rows:
            if not isinstance(row, Mapping):
                continue
            key = row.get("workstream_key")
            if not isinstance(key, str):
                continue
            rows[key] = row
            if bucket in {"active_projects", "review_candidates"}:
                active.add(key)
    return rows, active


def _snapshot_projects(
    snapshot: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    if snapshot is None:
        return []
    rows = snapshot.get("projects")
    if not isinstance(rows, list):
        raise InitiativePlanError([{"code": "initiative_snapshot_missing_projects"}])
    return [row for row in rows if isinstance(row, Mapping)]


def _snapshot_initiatives(
    snapshot: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    if snapshot is None:
        return []
    rows = snapshot.get("initiatives")
    if not isinstance(rows, list):
        raise InitiativePlanError([{"code": "initiative_snapshot_missing_initiatives"}])
    return [row for row in rows if isinstance(row, Mapping)]


def _desired_initiatives(strategy: Mapping[str, Any]) -> list[dict[str, Any]]:
    initiatives = _initiative_mapping(strategy.get("initiatives"), [])
    out: list[dict[str, Any]] = []
    for key in sorted(initiatives):
        row = initiatives[key]
        out.append({
            "initiative_key": key,
            "name": row["name"],
            "summary": row["summary"],
            "description": render_description(row),
            "status": row["status"],
            "priority": row["priority"],
            "health": row["health"],
            "owner_id": row["owner"],
            "lead_team": row["lead_team"],
            "target_date": row["target_date"],
            "labels": list(row["labels"]),
            "parent_initiative_ids": [],
        })
    return out


def _binding_rows(
    *,
    project_plan: Mapping[str, Any],
    strategy: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    project_by_key, active = _project_rows(project_plan)
    snapshot_by_key: dict[str, list[Mapping[str, Any]]] = {}
    for row in _snapshot_projects(snapshot):
        key = row.get("workstream_key")
        if isinstance(key, str):
            snapshot_by_key.setdefault(key, []).append(row)

    memberships = _membership_mapping(strategy.get("memberships"), [])
    initiative_rows = _initiative_mapping(strategy.get("initiatives"), [])
    out: list[dict[str, Any]] = []
    for workstream_key in sorted(memberships):
        source = project_by_key[workstream_key]
        matches = snapshot_by_key.get(workstream_key, [])
        bound_id = None
        if (
            len(matches) == 1
            and isinstance(matches[0].get("project_id"), str)
            and matches[0].get("project_id")
        ):
            bound_id = matches[0]["project_id"]
        initiative_key = memberships[workstream_key]
        out.append({
            "workstream_key": workstream_key,
            "initiative_key": initiative_key,
            "initiative_name": initiative_rows[initiative_key]["name"],
            "project_id": bound_id,
            "desired_project_name": source.get("desired_project_name"),
            "desired_project_status_class": source.get("desired_project_status_class"),
            "canonical_status": source.get("canonical_status"),
            "project_required": workstream_key in active,
        })
    return out


def _clean_string_list(raw: Any) -> tuple[list[str], bool]:
    """Return non-empty strings plus whether the original value was a valid list."""
    if not isinstance(raw, list):
        return [], False
    clean = [value for value in raw if isinstance(value, str) and value]
    return clean, len(clean) == len(raw)


def _current_membership_evidence(
    project: Mapping[str, Any],
    initiative_name_by_id: Mapping[str, str],
) -> dict[str, Any]:
    """Resolve membership without letting names override immutable IDs."""
    raw_names = project.get("initiative_names")
    if "initiative_ids" not in project:
        if raw_names is None:
            return {"initiative_ids": [], "names": [], "issues": []}
        names, names_valid = _clean_string_list(raw_names)
        issues: list[dict[str, Any]] = []
        if not names_valid:
            issues.append({
                "code": "membership_identity_conflict",
                "reason": "initiative_names_malformed",
            })
        return {"initiative_ids": [], "names": names, "issues": issues}

    issues: list[dict[str, Any]] = []
    raw_ids = project.get("initiative_ids")
    ids, ids_valid = _clean_string_list(raw_ids)
    if not ids_valid:
        issues.append({
            "code": "membership_identity_conflict",
            "reason": "initiative_ids_malformed",
        })

    duplicate_ids = sorted(
        initiative_id
        for initiative_id, count in Counter(ids).items()
        if count > 1
    )
    if duplicate_ids:
        issues.append({
            "code": "membership_duplicate_initiative_id",
            "initiative_ids": duplicate_ids,
        })

    unknown_ids = sorted({
        initiative_id
        for initiative_id in ids
        if initiative_id not in initiative_name_by_id
    })
    if unknown_ids:
        issues.append({
            "code": "membership_initiative_id_unknown",
            "initiative_ids": unknown_ids,
        })

    resolved_names = [
        initiative_name_by_id[initiative_id]
        for initiative_id in ids
        if initiative_id in initiative_name_by_id
    ]
    if len(set(ids)) > 1:
        issues.append({
            "code": "membership_multi_parent",
            "current_initiative_ids": sorted(set(ids)),
            "current_initiatives": sorted(set(resolved_names)),
        })

    if raw_names is not None:
        names, names_valid = _clean_string_list(raw_names)
        if not names_valid:
            issues.append({
                "code": "membership_identity_conflict",
                "reason": "initiative_names_malformed",
            })
        if Counter(names) != Counter(resolved_names):
            issues.append({
                "code": "membership_identity_conflict",
                "reason": "initiative_id_name_disagreement",
                "initiative_ids": sorted(ids),
                "resolved_names": sorted(resolved_names),
                "observed_names": sorted(names),
            })

    return {
        "initiative_ids": sorted(ids),
        "names": resolved_names,
        "issues": sorted(issues, key=lpp.canonical_bytes),
    }


def _current_membership_names(
    project: Mapping[str, Any],
    initiative_name_by_id: Mapping[str, str],
) -> list[str]:
    """Compatibility wrapper; IDs remain authoritative whenever supplied."""
    return list(_current_membership_evidence(project, initiative_name_by_id)["names"])


def initiative_drift(
    snapshot: Mapping[str, Any] | None,
    desired_initiatives: Sequence[Mapping[str, Any]],
    desired_memberships: Sequence[Mapping[str, Any]],
    exceptions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare one normalized witness to the exact approved desired state."""
    if snapshot is None:
        return []

    drift: list[dict[str, Any]] = []
    current_initiatives = _snapshot_initiatives(snapshot)
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    id_rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in current_initiatives:
        name = row.get("name")
        if isinstance(name, str):
            by_name.setdefault(name, []).append(row)
        initiative_id = row.get("initiative_id")
        if isinstance(initiative_id, str) and initiative_id:
            id_rows.setdefault(initiative_id, []).append(row)
        else:
            drift.append({
                "code": "initiative_id_ambiguous",
                "initiative_id": initiative_id,
                "name": name,
                "reason": "missing_or_empty",
            })

    id_to_name: dict[str, str] = {}
    for initiative_id, rows in sorted(id_rows.items()):
        names = sorted({
            row.get("name") for row in rows if isinstance(row.get("name"), str)
        })
        if len(rows) != 1 or len(names) != 1:
            drift.append({
                "code": "initiative_id_ambiguous",
                "initiative_id": initiative_id,
                "count": len(rows),
                "names": names,
            })
            continue
        id_to_name[initiative_id] = names[0]

    desired_names = {row["name"] for row in desired_initiatives}
    for desired in desired_initiatives:
        matches = by_name.get(desired["name"], [])
        if not matches:
            drift.append({
                "code": "initiative_missing",
                "initiative_key": desired["initiative_key"],
                "name": desired["name"],
            })
            continue
        if len(matches) > 1:
            drift.append({
                "code": "initiative_name_ambiguous",
                "initiative_key": desired["initiative_key"],
                "name": desired["name"],
                "count": len(matches),
            })
            continue

        current = matches[0]
        field_map = {
            "status": "status",
            "priority": "priority",
            "owner_id": "owner_id",
            "lead_team": "lead_team",
            "target_date": "target_date",
            "labels": "labels",
            "parent_initiative_ids": "parent_initiative_ids",
        }
        fields: list[str] = []
        for desired_field, current_field in field_map.items():
            current_value = current.get(current_field)
            desired_value = desired.get(desired_field)
            if desired_field in {"labels", "parent_initiative_ids"}:
                current_value = sorted(current_value) if isinstance(current_value, list) else current_value
                desired_value = sorted(desired_value) if isinstance(desired_value, list) else desired_value
            if current_value != desired_value:
                fields.append(desired_field)

        desired_health = desired.get("health")
        if desired_health is not None and current.get("health") != desired_health:
            fields.append("health")

        if fields:
            drift.append({
                "code": "initiative_field_drift",
                "initiative_key": desired["initiative_key"],
                "initiative_id": current.get("initiative_id"),
                "fields": sorted(fields),
            })

    for name, rows in sorted(by_name.items()):
        if name not in desired_names:
            for row in rows:
                drift.append({
                    "code": "unexpected_initiative",
                    "initiative_id": row.get("initiative_id"),
                    "name": name,
                })

    current_projects = _snapshot_projects(snapshot)
    project_id_rows: dict[str, list[Mapping[str, Any]]] = {}
    by_workstream: dict[str, list[Mapping[str, Any]]] = {}
    for row in current_projects:
        key = row.get("workstream_key")
        if isinstance(key, str):
            by_workstream.setdefault(key, []).append(row)
        project_id = row.get("project_id")
        if isinstance(project_id, str) and project_id:
            project_id_rows.setdefault(project_id, []).append(row)

    for project_id, rows in sorted(project_id_rows.items()):
        if len(rows) > 1:
            drift.append({
                "code": "project_id_ambiguous",
                "project_id": project_id,
                "count": len(rows),
                "workstream_keys": sorted({
                    row.get("workstream_key")
                    for row in rows
                    if isinstance(row.get("workstream_key"), str)
                }),
            })

    membership_evidence: dict[int, dict[str, Any]] = {}
    for project in current_projects:
        evidence = _current_membership_evidence(project, id_to_name)
        membership_evidence[id(project)] = evidence
        for issue in evidence["issues"]:
            drift.append({
                **issue,
                "workstream_key": project.get("workstream_key"),
                "project_id": project.get("project_id"),
            })

    desired_membership_by_key = {row["workstream_key"]: row for row in desired_memberships}
    for desired in desired_memberships:
        key = desired["workstream_key"]
        matches = by_workstream.get(key, [])
        if not matches:
            code = "project_create_required" if desired.get("project_required") else "project_binding_missing"
            drift.append({"code": code, "workstream_key": key})
            continue
        if len(matches) > 1:
            drift.append({
                "code": "project_binding_ambiguous",
                "workstream_key": key,
                "count": len(matches),
            })
            continue

        project = matches[0]
        project_id = project.get("project_id")
        if not isinstance(project_id, str) or not project_id:
            drift.append({"code": "project_binding_missing", "workstream_key": key})
            continue

        evidence = membership_evidence[id(project)]
        if evidence["issues"]:
            continue

        names = evidence["names"]
        if len(names) == 0:
            drift.append({
                "code": "membership_missing",
                "workstream_key": key,
                "project_id": project_id,
                "desired_initiative": desired["initiative_name"],
            })
        elif len(names) > 1:
            drift.append({
                "code": "membership_multi_parent",
                "workstream_key": key,
                "project_id": project_id,
                "current_initiatives": sorted(names),
            })
        elif names[0] != desired["initiative_name"]:
            drift.append({
                "code": "membership_wrong",
                "workstream_key": key,
                "project_id": project_id,
                "current_initiative": names[0],
                "desired_initiative": desired["initiative_name"],
            })

    exception_ws = {
        row.get("identity") for row in exceptions if row.get("identity_kind") == "workstream_key"
    }
    exception_ids = {
        row.get("identity") for row in exceptions if row.get("identity_kind") == "linear_project_id"
    }
    exception_key_counts = Counter(
        key
        for key in (project.get("workstream_key") for project in current_projects)
        if isinstance(key, str) and key in exception_ws
    )
    for key, count in sorted(exception_key_counts.items()):
        if count > 1:
            drift.append({
                "code": "project_binding_ambiguous",
                "workstream_key": key,
                "count": count,
            })

    for project in current_projects:
        key = project.get("workstream_key")
        project_id = project.get("project_id")
        is_exception = key in exception_ws or project_id in exception_ids
        evidence = membership_evidence[id(project)]
        names = evidence["names"]
        if is_exception:
            if names or project.get("initiative_ids"):
                drift.append({
                    "code": "exception_has_forbidden_membership",
                    "workstream_key": key,
                    "project_id": project_id,
                    "current_initiatives": sorted(names),
                })
            continue

        if isinstance(key, str) and key in desired_membership_by_key:
            continue

        drift.append({
            "code": "unmapped_visible_project",
            "workstream_key": key,
            "project_id": project_id,
            "name": project.get("name"),
        })

    return sorted(drift, key=lpp.canonical_bytes)


def compile_initiative_plan(
    *,
    project_plan: Mapping[str, Any],
    strategy_path: Path,
    snapshot_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile Initiative desired state from an already-compiled Project plan."""
    strategy = load_strategy(strategy_path)
    validate_strategy(strategy, project_plan)
    snapshot = _load_snapshot(snapshot_path)

    desired_initiatives = _desired_initiatives(strategy)
    desired_memberships = _binding_rows(
        project_plan=project_plan,
        strategy=strategy,
        snapshot=snapshot,
    )
    exceptions = [
        dict(row)
        for row in strategy.get("unassigned_exceptions", [])
        if isinstance(row, Mapping)
    ]
    exceptions = sorted(exceptions, key=lpp.canonical_bytes)
    drift = initiative_drift(snapshot, desired_initiatives, desired_memberships, exceptions)
    hard_blockers = [row for row in drift if row["code"] in _HARD_DRIFT_CODES]
    drift_counts = dict(sorted(Counter(row["code"] for row in drift).items()))
    group_counts = dict(sorted(Counter(row["initiative_key"] for row in desired_memberships).items()))

    semantic: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "source_design": dict(strategy.get("source_design", {})),
        "project_plan_semantic_hash": project_plan.get("semantic_hash"),
        "desired_initiatives": desired_initiatives,
        "desired_memberships": desired_memberships,
        "unassigned_exceptions": exceptions,
        "drift": drift,
        "hard_blockers": hard_blockers,
        "summary": {
            "desired_initiatives": len(desired_initiatives),
            "desired_memberships": len(desired_memberships),
            "unassigned_exceptions": len(exceptions),
            "group_counts": group_counts,
            "drift_counts": drift_counts,
            "hard_blockers": len(hard_blockers),
        },
    }
    digest = hashlib.sha256(lpp.canonical_bytes(semantic)).hexdigest()
    plan = {**semantic, "semantic_hash": digest}
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "compiled",
        "strategy_source_revision": strategy.get("source_design", {}).get("protected_revision"),
        "project_plan_semantic_hash": project_plan.get("semantic_hash"),
        "initiative_plan_semantic_hash": digest,
        "desired_counts": {
            "initiatives": len(desired_initiatives),
            "memberships": len(desired_memberships),
            "exceptions": len(exceptions),
        },
        "group_counts": group_counts,
        "exception_bindings": exceptions,
        "drift_code_counts": drift_counts,
        "snapshot_supplied": snapshot_path is not None,
    }
    return plan, receipt
