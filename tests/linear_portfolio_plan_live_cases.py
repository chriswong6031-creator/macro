from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from scripts import linear_portfolio_plan as lpp


LINEAR_SNAPSHOT = Path("research/linear_portfolio_p0/linear_snapshot_2026-08-21.json")


def _warning_keys(plan):
    grouped = defaultdict(list)
    for warning in plan["warnings"]:
        key = warning.get("workstream_key")
        if key is not None:
            grouped[warning["code"]].append(key)
    return {
        code: sorted(set(keys))
        for code, keys in sorted(grouped.items())
    }


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

    snapshot_path = repo / LINEAR_SNAPSHOT
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["schema"] == lpp.LINEAR_SNAPSHOT_SCHEMA
    assert snapshot["source"]["authority"] == "witness_only_not_canonical"

    with_linear, with_linear_receipt = lpp.compile_plan(
        repo / "agentos",
        linear_snapshot_path=snapshot_path,
        **kwargs,
    )
    with_linear_repeat, _ = lpp.compile_plan(
        repo / "agentos",
        linear_snapshot_path=snapshot_path,
        **kwargs,
    )
    assert lpp.semantic_json(with_linear) == lpp.semantic_json(with_linear_repeat)

    proof = {
        "schema": "linear_portfolio_plan_ci_receipt.v1",
        "source_revision": os.environ.get("GITHUB_SHA", "local-checkout"),
        "semantic_hash_without_linear_snapshot": first["semantic_hash"],
        "semantic_hash_with_linear_snapshot": with_linear["semantic_hash"],
        "active_keys": [row["workstream_key"] for row in first["active_projects"]],
        "review_candidate_keys": [
            row["workstream_key"] for row in first["review_candidates"]
        ],
        "excluded_keys": [row["workstream_key"] for row in first["excluded_projects"]],
        "warning_counts_without_linear_snapshot": dict(
            sorted(Counter(row["code"] for row in first["warnings"]).items())
        ),
        "warning_counts_with_linear_snapshot": with_linear_receipt["warning_counts"],
        "linear_drift_keys": _warning_keys(with_linear),
        "linear_snapshot_path": LINEAR_SNAPSHOT.as_posix(),
        "linear_snapshot_projects": len(snapshot["projects"]),
        "linear_snapshot_authority": snapshot["source"]["authority"],
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
