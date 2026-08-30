from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from scripts import linear_initiative_plan as lip
from scripts import linear_portfolio_plan as lpp


STRATEGY_REL = Path("config/linear_initiative_portfolio.v1.json")
SNAPSHOT_REL = Path(
    "research/linear_initiative_portfolio/linear_initiative_snapshot_2026-08-29.json"
)
EXPECTED_GROUP_COUNTS = {
    "autonomous-ai-organization": 3,
    "canonical-intelligence-substrate-learning": 10,
    "global-markets-regimes-risk-command": 5,
    "institutional-company-event-intelligence": 11,
    "legendary-alpha-discovery-timing": 15,
    "personal-institutional-desk": 3,
    "trusted-production-customer-platform": 5,
}


def test_current_repository_initiative_plan_is_deterministic_and_emits_ci_receipt(
    pytestconfig,
):
    repo = Path(__file__).resolve().parents[1]
    strategy_path = repo / STRATEGY_REL
    snapshot_path = repo / SNAPSHOT_REL

    project_plan, _project_receipt = lpp.compile_plan(
        repo / "agentos",
        programs=lpp.agentos._load_programs(),
        generated_state_path=repo / "data" / "governance" / "agent_os_state.json",
    )
    selected_snapshot = snapshot_path if snapshot_path.exists() else None

    first, receipt = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=strategy_path,
        snapshot_path=selected_snapshot,
    )
    second, _ = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=strategy_path,
        snapshot_path=selected_snapshot,
    )

    assert lpp.semantic_json(first) == lpp.semantic_json(second)
    assert first["schema"] == lip.PLAN_SCHEMA
    assert len(first["desired_initiatives"]) == 7
    assert len(first["desired_memberships"]) == 52
    assert len(first["unassigned_exceptions"]) == 2
    assert first["summary"]["group_counts"] == EXPECTED_GROUP_COUNTS
    assert receipt["initiative_plan_semantic_hash"] == first["semantic_hash"]
    assert receipt["project_plan_semantic_hash"] == project_plan["semantic_hash"]

    exceptions = {
        (row["identity_kind"], row["identity"], row["reason"])
        for row in first["unassigned_exceptions"]
    }
    assert exceptions == {
        ("workstream_key", "WS:WATCHLIST-PORTFOLIO-CEO", "compatibility_redirect"),
        (
            "linear_project_id",
            "9aef6461-306a-4a3c-911b-c6a4b6635a78",
            "canonical_parent_unresolved",
        ),
    }

    drift_counts = dict(sorted(Counter(row["code"] for row in first["drift"]).items()))
    proof = {
        "schema": "linear_initiative_plan_ci_receipt.v1",
        "source_revision": os.environ.get("GITHUB_SHA", "local-checkout"),
        "strategy_path": STRATEGY_REL.as_posix(),
        "strategy_source_revision": receipt["strategy_source_revision"],
        "project_plan_semantic_hash": project_plan["semantic_hash"],
        "initiative_plan_semantic_hash": first["semantic_hash"],
        "desired_counts": receipt["desired_counts"],
        "group_counts": receipt["group_counts"],
        "exception_bindings": receipt["exception_bindings"],
        "drift_code_counts": drift_counts,
        "snapshot_path": SNAPSHOT_REL.as_posix() if selected_snapshot else None,
        "snapshot_supplied": selected_snapshot is not None,
        "hard_blocker_count": len(first["hard_blockers"]),
    }
    rendered = json.dumps(proof, ensure_ascii=False, sort_keys=True)

    terminal = pytestconfig.pluginmanager.getplugin("terminalreporter")
    if terminal is not None:
        terminal.write_line("LINEAR_INITIATIVE_PLAN_RECEIPT=" + rendered)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n## Linear Initiative desired-state receipt\n\n```json\n")
            handle.write(json.dumps(proof, ensure_ascii=False, sort_keys=True, indent=2))
            handle.write("\n```\n")
