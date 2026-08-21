from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from scripts import linear_portfolio_plan as lpp


def test_current_repository_plan_is_deterministic_and_emits_ci_receipt(pytestconfig):
    repo = Path(__file__).resolve().parents[1]
    kwargs = {
        "programs": lpp.agentos._load_programs(),
        "generated_state_path": repo / "data" / "governance" / "agent_os_state.json",
    }
    first, receipt = lpp.compile_plan(repo / "agentos", **kwargs)
    second, _ = lpp.compile_plan(repo / "agentos", **kwargs)

    assert lpp.semantic_json(first) == lpp.semantic_json(second)
    assert first["schema"] == lpp.PLAN_SCHEMA
    assert "issues" not in first
    assert (
        len(first["active_projects"])
        + len(first["review_candidates"])
        + len(first["excluded_projects"])
        == receipt["record_counts"]["workstreams"]
    )
    assert all(
        row["source_path"].startswith("agentos/workstreams/")
        for bucket in ("active_projects", "review_candidates", "excluded_projects")
        for row in first[bucket]
    )

    proof = {
        "schema": "linear_portfolio_plan_ci_receipt.v1",
        "source_revision": os.environ.get("GITHUB_SHA", "local-checkout"),
        "semantic_hash": first["semantic_hash"],
        "active_keys": [row["workstream_key"] for row in first["active_projects"]],
        "review_candidate_keys": [
            row["workstream_key"] for row in first["review_candidates"]
        ],
        "excluded_keys": [row["workstream_key"] for row in first["excluded_projects"]],
        "warning_counts": dict(
            sorted(Counter(row["code"] for row in first["warnings"]).items())
        ),
        "record_counts": receipt["record_counts"],
        "validator_warning_count": receipt["validator_warning_count"],
    }
    rendered = json.dumps(proof, ensure_ascii=False, sort_keys=True)

    terminal = pytestconfig.pluginmanager.getplugin("terminalreporter")
    if terminal is not None:
        terminal.write_line("MAS65_LINEAR_PORTFOLIO_PLAN_RECEIPT=" + rendered)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write("\n## MAS-65 real-checkout projector receipt\n\n```json\n")
            handle.write(json.dumps(proof, ensure_ascii=False, sort_keys=True, indent=2))
            handle.write("\n```\n")
