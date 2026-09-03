#!/usr/bin/env python3
"""Current-epoch facade for the deterministic Linear Initiative compiler.

The implementation remains in ``scripts.linear_initiative_plan_legacy`` so the
existing public API and drift semantics stay intact. This facade freezes the
protected workspace-level 7/62/2 source contract and keeps the canonical import
path stable.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from scripts import linear_initiative_plan_legacy as _legacy

# Preserve the complete established API, including helper names used by tests
# and downstream tooling, before overriding the current-epoch seams below.
globals().update({
    name: value
    for name, value in vars(_legacy).items()
    if not name.startswith("__")
})

_EXPECTED_INITIATIVE_FIELDS = {
    "status": "Active",
    "lead_team": None,
    "owner": None,
    "target_date": None,
    "health": None,
    "labels": [],
    "parent_initiatives": [],
}
_EXPECTED_SOURCE_IDENTITY = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "path": (
        "docs/superpowers/specs/"
        "2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md"
    ),
    "protected_revision": "84d74cf9c7b81ba70169ab7df1f71835da2d297b",
}
_EXPECTED_CURRENT_MEMBERSHIPS = {
    "WS:ALPHA-INTELLIGENCE-INTEGRATION": "canonical-intelligence-substrate-learning",
    "WS:GMI-THEME-GRAPH": "canonical-intelligence-substrate-learning",
    "WS:STOCK-IDENTITY": "canonical-intelligence-substrate-learning",
    "WS:MARKET-MEMORY-W2C": "canonical-intelligence-substrate-learning",
    "WS:MASSIVE-STOCK-DAY-R2-COHERENCE": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-MEASUREMENT-LAW": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-EVIDENCE-VIEW": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-T1-ENGINE-REGISTRY": "canonical-intelligence-substrate-learning",
    "WS:EVAL-OS-OUTPUT-HEALTH": "canonical-intelligence-substrate-learning",
    "WS:CROSS-REPO-CONTRACT-GOVERNANCE": "canonical-intelligence-substrate-learning",
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
    "WS:PROPHET-CANDIDATE-ADDED-DATE": "legendary-alpha-discovery-timing",
    "WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE": "legendary-alpha-discovery-timing",
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
    "WS:FLOW-OBSERVATORY-V2": "global-markets-regimes-risk-command",
    "WS:MARKET-OS": "personal-institutional-desk",
    "WS:STOCK-DOSSIER-LIVE-QUOTE": "personal-institutional-desk",
    "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2": "personal-institutional-desk",
    "WS:REACTIVE-PROJECTION": "personal-institutional-desk",
    "WS:ACCOUNT-IDENTITY-HARDENING": "trusted-production-customer-platform",
    "WS:CUSTOMER-DATA-BACKUP": "trusted-production-customer-platform",
    "WS:COMMERCIAL-PATH-ALERTING": "trusted-production-customer-platform",
    "WS:CI-MERGE-CONTROL-PLANE": "trusted-production-customer-platform",
    "WS:RUNNER-FLEET-RESILIENCE": "trusted-production-customer-platform",
    "WS:EXECUTIVE-OS-DISASTER-RECOVERY": "trusted-production-customer-platform",
    "WS:REPRODUCIBLE-WORKER-ENVIRONMENTS": "trusted-production-customer-platform",
    "WS:TERMINAL-GITHUB-CANONICALIZATION": "trusted-production-customer-platform",
    "WS:AGENT-OS": "autonomous-ai-organization",
    "WS:CHAIRMAN-CONTROL-ROOM": "autonomous-ai-organization",
    "WS:EXECUTIVE-CAPACITY-FABRIC": "autonomous-ai-organization",
    "WS:AGENT-EVAL-FABRIC": "autonomous-ai-organization",
    "WS:CODE-INTELLIGENCE-FABRIC": "autonomous-ai-organization",
    "WS:EXECUTIVE-ATTENTION-ECONOMICS": "autonomous-ai-organization",
    "WS:OPERATION-ASSURANCE": "autonomous-ai-organization",
}
_EXPECTED_GROUP_COUNTS = {
    "autonomous-ai-organization": 7,
    "canonical-intelligence-substrate-learning": 10,
    "global-markets-regimes-risk-command": 6,
    "institutional-company-event-intelligence": 11,
    "legendary-alpha-discovery-timing": 16,
    "personal-institutional-desk": 4,
    "trusted-production-customer-platform": 8,
}
_PARKED_WORKSTREAM = "WS:TERMINAL-GITHUB-CANONICAL-DEPLOYMENT"

# The established helpers read these module globals, so pin the legacy
# implementation to the same protected current epoch.
_legacy._EXPECTED_INITIATIVE_FIELDS = _EXPECTED_INITIATIVE_FIELDS
_legacy._EXPECTED_SOURCE_IDENTITY = _EXPECTED_SOURCE_IDENTITY


def validate_strategy(
    strategy: Mapping[str, Any],
    project_plan: Mapping[str, Any],
) -> None:
    """Fail closed unless the exact protected workspace-level 7/62/2 contract holds."""
    failures: list[dict[str, Any]] = []
    if strategy.get("schema") != STRATEGY_SCHEMA:
        failures.append({"code": "strategy_wrong_schema"})

    source_design = strategy.get("source_design")
    if not isinstance(source_design, Mapping):
        source_fields = sorted(_EXPECTED_SOURCE_IDENTITY)
    else:
        source_fields = sorted(
            field
            for field, expected in _EXPECTED_SOURCE_IDENTITY.items()
            if source_design.get(field) != expected
        )
    if source_fields:
        failures.append({
            "code": "strategy_source_design_invalid",
            "fields": source_fields,
        })

    initiatives = _legacy._initiative_mapping(strategy.get("initiatives"), failures)
    if len(initiatives) != len(_legacy._EXPECTED_INITIATIVES):
        failures.append({
            "code": "strategy_initiative_count_mismatch",
            "expected": len(_legacy._EXPECTED_INITIATIVES),
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

        expected = _legacy._EXPECTED_INITIATIVES.get(key)
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
        for field in _legacy._REQUIRED_PROSE_FIELDS:
            if not isinstance(row.get(field), str) or not row[field].strip():
                mismatched.append(field)
        if mismatched:
            failures.append({
                "code": "strategy_initiative_field_mismatch",
                "initiative_key": key,
                "fields": sorted(set(mismatched)),
            })

    memberships = _legacy._membership_mapping(strategy.get("memberships"), failures)
    if len(memberships) != len(_EXPECTED_CURRENT_MEMBERSHIPS):
        failures.append({
            "code": "strategy_membership_count_mismatch",
            "expected": len(_EXPECTED_CURRENT_MEMBERSHIPS),
            "actual": len(memberships),
        })
    if memberships != _EXPECTED_CURRENT_MEMBERSHIPS:
        failures.append({
            "code": "strategy_current_membership_mismatch",
            "missing": sorted(
                key
                for key, value in _EXPECTED_CURRENT_MEMBERSHIPS.items()
                if memberships.get(key) != value
            ),
            "unexpected": sorted(
                key
                for key in memberships
                if key not in _EXPECTED_CURRENT_MEMBERSHIPS
            ),
        })

    group_counts = dict(sorted(Counter(memberships.values()).items()))
    if group_counts != _EXPECTED_GROUP_COUNTS:
        failures.append({
            "code": "strategy_group_counts_mismatch",
            "expected": _EXPECTED_GROUP_COUNTS,
            "actual": group_counts,
        })
    if _PARKED_WORKSTREAM in memberships:
        failures.append({
            "code": "strategy_parked_workstream_mapped",
            "workstream_key": _PARKED_WORKSTREAM,
        })

    initiative_keys = set(_legacy._EXPECTED_INITIATIVES)
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
    if exception_set != _legacy._EXPECTED_EXCEPTIONS:
        failures.append({
            "code": "strategy_exception_mismatch",
            "expected": sorted(_legacy._EXPECTED_EXCEPTIONS),
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

    universe, active = _legacy._project_keys(project_plan)
    for workstream_key in sorted(memberships):
        if workstream_key not in universe:
            failures.append({
                "code": "strategy_membership_unknown_workstream",
                "workstream_key": workstream_key,
            })

    for workstream_key in sorted(active):
        if (
            workstream_key not in memberships
            and workstream_key != _legacy._WATCHLIST_EXCEPTION
        ):
            failures.append({
                "code": "strategy_unmapped_active_workstream",
                "workstream_key": workstream_key,
            })

    if failures:
        raise InitiativePlanError(failures)


# The established compiler resolves ``validate_strategy`` through its own
# module globals. Bind that seam once so every canonical call uses this epoch.
_legacy.validate_strategy = validate_strategy


def compile_initiative_plan(
    *,
    project_plan: Mapping[str, Any],
    strategy_path: Path,
    snapshot_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile through the established implementation and expose top-level hash receipts."""
    plan, receipt = _legacy.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=strategy_path,
        snapshot_path=snapshot_path,
    )
    provenance = receipt["strategy_provenance"]
    receipt["strategy_content_sha256"] = provenance["strategy_content_sha256"]
    receipt["desired_memberships_sha256"] = provenance["desired_memberships_sha256"]
    return plan, receipt
