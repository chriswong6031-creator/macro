from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import pytest

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
EXPECTED_SOURCE_IDENTITY = {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "path": "docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md",
    "protected_revision": "d004f5bf7953e943281dff7efd8fe17a54b0cf6c",
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
    assert receipt["strategy_provenance"]["source_identity"] == EXPECTED_SOURCE_IDENTITY
    assert receipt["strategy_provenance"]["strategy_content_sha256"] == hashlib.sha256(
        strategy_path.read_bytes()
    ).hexdigest()
    assert receipt["strategy_provenance"]["desired_memberships_sha256"] == hashlib.sha256(
        lpp.canonical_bytes(first["desired_memberships"])
    ).hexdigest()

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
        "strategy_provenance": receipt["strategy_provenance"],
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


def _initiative(initiative_id: str, name: str, key: str) -> tuple[dict, dict]:
    desired = {
        "initiative_key": key,
        "name": name,
        "status": "Active",
        "priority": 1,
        "health": None,
        "owner_id": None,
        "lead_team": "MastermindX",
        "target_date": None,
        "labels": [],
        "parent_initiative_ids": [],
    }
    current = {
        "initiative_id": initiative_id,
        "name": name,
        "status": "Active",
        "priority": 1,
        "health": None,
        "owner_id": None,
        "lead_team": "MastermindX",
        "target_date": None,
        "labels": [],
        "parent_initiative_ids": [],
    }
    return desired, current


def _project(
    workstream_key: str,
    project_id: str,
    *,
    initiative_ids: list[str],
    initiative_names: list[str],
) -> dict:
    return {
        "workstream_key": workstream_key,
        "project_id": project_id,
        "name": workstream_key,
        "initiative_ids": initiative_ids,
        "initiative_names": initiative_names,
    }


def _membership(workstream_key: str, initiative_name: str) -> dict:
    return {
        "workstream_key": workstream_key,
        "initiative_name": initiative_name,
        "project_required": True,
    }


def _snapshot(initiatives: list[dict], projects: list[dict]) -> dict:
    return {
        "schema": lip.SNAPSHOT_SCHEMA,
        "initiatives": initiatives,
        "projects": projects,
    }


def _drift_codes(
    *,
    desired_initiatives: list[dict],
    current_initiatives: list[dict],
    desired_memberships: list[dict],
    projects: list[dict],
) -> list[str]:
    drift = lip.initiative_drift(
        _snapshot(current_initiatives, projects),
        desired_initiatives,
        desired_memberships,
        [],
    )
    return [row["code"] for row in drift]


def test_membership_names_cannot_hide_a_wrong_known_initiative_id():
    desired, desired_current = _initiative("init-desired", "Desired", "desired")
    other, other_current = _initiative("init-other", "Other", "other")

    codes = _drift_codes(
        desired_initiatives=[desired, other],
        current_initiatives=[desired_current, other_current],
        desired_memberships=[_membership("WS:A", "Desired")],
        projects=[
            _project(
                "WS:A",
                "project-a",
                initiative_ids=["init-other"],
                initiative_names=["Desired"],
            )
        ],
    )

    assert "membership_identity_conflict" in codes
    assert "membership_identity_conflict" in lip._HARD_DRIFT_CODES


def test_membership_names_cannot_hide_an_unknown_initiative_id():
    desired, desired_current = _initiative("init-desired", "Desired", "desired")

    codes = _drift_codes(
        desired_initiatives=[desired],
        current_initiatives=[desired_current],
        desired_memberships=[_membership("WS:A", "Desired")],
        projects=[
            _project(
                "WS:A",
                "project-a",
                initiative_ids=["init-unknown"],
                initiative_names=["Desired"],
            )
        ],
    )

    assert "membership_initiative_id_unknown" in codes
    assert "membership_initiative_id_unknown" in lip._HARD_DRIFT_CODES


def test_one_display_name_cannot_hide_two_initiative_ids():
    desired, desired_current = _initiative("init-desired", "Desired", "desired")
    other, other_current = _initiative("init-other", "Other", "other")

    codes = _drift_codes(
        desired_initiatives=[desired, other],
        current_initiatives=[desired_current, other_current],
        desired_memberships=[_membership("WS:A", "Desired")],
        projects=[
            _project(
                "WS:A",
                "project-a",
                initiative_ids=["init-desired", "init-other"],
                initiative_names=["Desired"],
            )
        ],
    )

    assert "membership_multi_parent" in codes
    assert "membership_multi_parent" in lip._HARD_DRIFT_CODES


def test_wrong_display_name_cannot_override_the_correct_initiative_id():
    desired, desired_current = _initiative("init-desired", "Desired", "desired")
    other, other_current = _initiative("init-other", "Other", "other")

    codes = _drift_codes(
        desired_initiatives=[desired, other],
        current_initiatives=[desired_current, other_current],
        desired_memberships=[_membership("WS:A", "Desired")],
        projects=[
            _project(
                "WS:A",
                "project-a",
                initiative_ids=["init-desired"],
                initiative_names=["Other"],
            )
        ],
    )

    assert "membership_identity_conflict" in codes
    assert "membership_identity_conflict" in lip._HARD_DRIFT_CODES


def test_duplicate_initiative_id_evidence_is_ambiguous():
    desired, desired_current = _initiative("init-shared", "Desired", "desired")
    other, other_current = _initiative("init-shared", "Other", "other")

    codes = _drift_codes(
        desired_initiatives=[desired, other],
        current_initiatives=[desired_current, other_current],
        desired_memberships=[_membership("WS:A", "Desired")],
        projects=[
            _project(
                "WS:A",
                "project-a",
                initiative_ids=["init-shared"],
                initiative_names=["Desired"],
            )
        ],
    )

    assert "initiative_id_ambiguous" in codes
    assert "initiative_id_ambiguous" in lip._HARD_DRIFT_CODES


def test_duplicate_project_id_evidence_is_ambiguous():
    desired, desired_current = _initiative("init-desired", "Desired", "desired")

    codes = _drift_codes(
        desired_initiatives=[desired],
        current_initiatives=[desired_current],
        desired_memberships=[
            _membership("WS:A", "Desired"),
            _membership("WS:B", "Desired"),
        ],
        projects=[
            _project(
                "WS:A",
                "project-shared",
                initiative_ids=["init-desired"],
                initiative_names=["Desired"],
            ),
            _project(
                "WS:B",
                "project-shared",
                initiative_ids=["init-desired"],
                initiative_names=["Desired"],
            ),
        ],
    )

    assert "project_id_ambiguous" in codes
    assert "project_id_ambiguous" in lip._HARD_DRIFT_CODES


def test_conflicting_identity_evidence_is_input_order_invariant():
    desired, desired_current = _initiative("init-shared", "Desired", "desired")
    other, other_current = _initiative("init-shared", "Other", "other")
    project = _project(
        "WS:A",
        "project-a",
        initiative_ids=["init-shared"],
        initiative_names=[],
    )

    first = lip.initiative_drift(
        _snapshot([desired_current, other_current], [project]),
        [desired, other],
        [_membership("WS:A", "Desired")],
        [],
    )
    second = lip.initiative_drift(
        _snapshot([other_current, desired_current], [project]),
        [desired, other],
        [_membership("WS:A", "Desired")],
        [],
    )

    assert first == second
    assert "initiative_id_ambiguous" in {row["code"] for row in first}


def _strategy_project_plan(strategy: dict) -> dict:
    keys = sorted(strategy["memberships"])
    return {
        "schema": lpp.PLAN_SCHEMA,
        "semantic_hash": "strategy-project-plan-fixture",
        "active_projects": [
            {
                "workstream_key": key,
                "desired_project_name": key,
                "desired_project_status_class": "started",
                "canonical_status": "active",
            }
            for key in keys + ["WS:WATCHLIST-PORTFOLIO-CEO"]
        ],
        "review_candidates": [],
        "excluded_projects": [],
    }


def _write_strategy(tmp_path: Path, strategy: dict, name: str) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(strategy, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def test_snapshot_initiative_rows_fail_closed_with_collection_and_index():
    desired_a, current_a = _initiative("init-a", "A", "a")
    desired_b, current_b = _initiative("init-b", "B", "b")

    for malformed in (None, "not-an-object", ["not-an-object"]):
        for rows in ([current_a, malformed, current_b], [current_b, malformed, current_a]):
            snapshot = {
                "schema": lip.SNAPSHOT_SCHEMA,
                "initiatives": rows,
                "projects": [],
            }
            with pytest.raises(lip.InitiativePlanError) as exc:
                lip.initiative_drift(snapshot, [desired_a, desired_b], [], [])
            assert exc.value.failures == (
                {
                    "code": "initiative_snapshot_row_malformed",
                    "collection": "initiatives",
                    "row_index": 1,
                },
            )


def test_snapshot_project_rows_fail_closed_with_collection_and_index():
    desired, current = _initiative("init-a", "A", "a")
    valid_project = _project(
        "WS:A",
        "project-a",
        initiative_ids=["init-a"],
        initiative_names=["A"],
    )

    for malformed in (None, "not-an-object", ["not-an-object"]):
        for rows in ([valid_project, malformed], [malformed, valid_project]):
            expected_index = 1 if rows[1] is malformed else 0
            snapshot = {
                "schema": lip.SNAPSHOT_SCHEMA,
                "initiatives": [current],
                "projects": rows,
            }
            with pytest.raises(lip.InitiativePlanError) as exc:
                lip.initiative_drift(snapshot, [desired], [], [])
            assert exc.value.failures == (
                {
                    "code": "initiative_snapshot_row_malformed",
                    "collection": "projects",
                    "row_index": expected_index,
                },
            )


@pytest.mark.parametrize(
    "source_design,bad_fields",
    [
        (None, ["path", "protected_revision", "repository"]),
        ([], ["path", "protected_revision", "repository"]),
        (
            {**EXPECTED_SOURCE_IDENTITY, "repository": "wrong/repository"},
            ["repository"],
        ),
        (
            {**EXPECTED_SOURCE_IDENTITY, "path": "docs/wrong.md"},
            ["path"],
        ),
        (
            {**EXPECTED_SOURCE_IDENTITY, "protected_revision": "not-a-40-hex-revision"},
            ["protected_revision"],
        ),
        (
            {**EXPECTED_SOURCE_IDENTITY, "protected_revision": "0" * 40},
            ["protected_revision"],
        ),
    ],
)
def test_strategy_source_design_is_closed_and_exact(source_design, bad_fields):
    repo = Path(__file__).resolve().parents[1]
    strategy = json.loads((repo / STRATEGY_REL).read_text(encoding="utf-8"))
    strategy["source_design"] = source_design

    with pytest.raises(lip.InitiativePlanError) as exc:
        lip.validate_strategy(strategy, _strategy_project_plan(strategy))

    assert exc.value.failures == (
        {
            "code": "strategy_source_design_invalid",
            "fields": bad_fields,
        },
    )


def test_strategy_receipt_binds_exact_source_bytes_and_membership_rows(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    strategy_path = repo / STRATEGY_REL
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    project_plan = _strategy_project_plan(strategy)

    plan, receipt = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=strategy_path,
    )
    repeat_plan, repeat_receipt = lip.compile_initiative_plan(
        project_plan=project_plan,
        strategy_path=strategy_path,
    )

    assert repeat_plan == plan
    assert repeat_receipt == receipt
    provenance = receipt["strategy_provenance"]
    assert provenance["source_identity"] == EXPECTED_SOURCE_IDENTITY
    assert provenance["strategy_content_sha256"] == hashlib.sha256(
        strategy_path.read_bytes()
    ).hexdigest()
    assert provenance["desired_memberships_sha256"] == hashlib.sha256(
        lpp.canonical_bytes(plan["desired_memberships"])
    ).hexdigest()

    mutated = json.loads(json.dumps(strategy))
    mutated["memberships"]["WS:MARKET-OS"] = "autonomous-ai-organization"
    mutated_path = _write_strategy(tmp_path, mutated, "mutated-strategy.json")
    mutated_plan, mutated_receipt = lip.compile_initiative_plan(
        project_plan=_strategy_project_plan(mutated),
        strategy_path=mutated_path,
    )
    assert len(mutated_plan["desired_memberships"]) == 52
    assert (
        mutated_receipt["strategy_provenance"]["desired_memberships_sha256"]
        != provenance["desired_memberships_sha256"]
    )
