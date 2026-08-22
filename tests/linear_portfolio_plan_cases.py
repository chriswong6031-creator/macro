from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from scripts import linear_portfolio_plan as lpp


def _record(
    key: str,
    status: str,
    *,
    title: str | None = None,
    next_action: str = "Do the next bounded thing.",
    waves=None,
    needs_ceo=None,
    blocked_by=None,
) -> str:
    rows = waves if waves is not None else [
        {"id": "W0", "title": "First wave", "status": "todo"}
    ]
    doc = {
        "key": key,
        "title": title or key.title(),
        "objective": f"Objective for {key}.",
        "status": status,
        "program": "test-program",
        "repos": ["macro"],
        "owner": "coo-fable",
        "class": "build",
        "blast_radius": "reversible",
        "ambiguity": "specified",
        "waves": rows,
        "next_action": next_action,
    }
    if needs_ceo is not None:
        doc["needs_ceo"] = needs_ceo
    if blocked_by is not None:
        doc["blocked_by"] = blocked_by
    import yaml

    return "---\n" + yaml.safe_dump(doc, sort_keys=False) + "---\nBody.\n"


def _store(tmp_path: Path, specs):
    root = tmp_path / "agentos"
    (root / "workstreams").mkdir(parents=True)
    for key, status, kwargs in specs:
        (root / "workstreams" / f"WS-{key}.md").write_text(
            _record(key, status, **kwargs), encoding="utf-8"
        )
    return root


def _compile(root: Path, **kwargs):
    return lpp.compile_plan(
        root,
        programs=None,
        generated_state_path=kwargs.pop("generated_state_path", None),
        **kwargs,
    )[0]


def test_selection_law_and_wave_observation(tmp_path):
    root = _store(
        tmp_path,
        [
            ("ACTIVE", "active", {}),
            ("BLOCKED", "blocked", {"blocked_by": ["named cause"]}),
            ("CI", "awaiting_ci", {}),
            ("REVIEW", "awaiting_review", {}),
            ("PROPOSED", "proposed", {}),
            ("DONE", "done", {}),
            ("PARKED", "parked", {}),
            ("KILLED", "killed", {}),
        ],
    )
    plan = _compile(root)
    assert [row["workstream_key"] for row in plan["active_projects"]] == [
        "WS:ACTIVE",
        "WS:BLOCKED",
        "WS:CI",
        "WS:REVIEW",
    ]
    assert [row["workstream_key"] for row in plan["review_candidates"]] == [
        "WS:PROPOSED"
    ]
    assert [row["workstream_key"] for row in plan["excluded_projects"]] == [
        "WS:DONE",
        "WS:KILLED",
        "WS:PARKED",
    ]
    assert plan["active_projects"][0]["non_done_waves"][0]["id"] == "W0"
    assert "issues" not in plan


def test_generated_state_is_only_a_drift_witness(tmp_path):
    root = _store(tmp_path, [("ALPHA", "active", {})])
    generated = tmp_path / "agent_os_state.json"
    generated.write_text(
        json.dumps(
            {
                "schema": "agent_os_state.v1",
                "workstreams": [{"key": "ALPHA", "status": "done"}],
            }
        )
    )
    plan = _compile(root, generated_state_path=generated)
    assert plan["active_projects"][0]["canonical_status"] == "active"
    assert any(
        warning["code"] == "generated_state_disagrees_with_direct_record"
        for warning in plan["warnings"]
    )


def test_similar_titles_do_not_collide(tmp_path):
    root = _store(
        tmp_path,
        [
            ("FOO", "active", {"title": "Same title"}),
            ("FOO-V2", "active", {"title": "Same title"}),
        ],
    )
    plan = _compile(root)
    assert [row["workstream_key"] for row in plan["active_projects"]] == [
        "WS:FOO",
        "WS:FOO-V2",
    ]
    assert (
        plan["active_projects"][0]["desired_project_name"]
        != plan["active_projects"][1]["desired_project_name"]
    )


def test_same_tree_is_byte_identical_and_has_no_absolute_paths(tmp_path):
    root = _store(tmp_path, [("ALPHA", "active", {})])
    first = _compile(root)
    second = _compile(root)
    assert lpp.semantic_json(first) == lpp.semantic_json(second)
    assert str(tmp_path) not in lpp.semantic_json(first)


def test_yaml_mapping_order_does_not_change_semantic_plan(tmp_path):
    root = _store(tmp_path, [("ALPHA", "active", {})])
    path = root / "workstreams" / "WS-ALPHA.md"
    first = _compile(root)
    first_hash = first["active_projects"][0]["source_content_sha256"]

    rec, body = lpp.agentos.parse_record(path)
    import yaml

    path.write_text(
        "---\n" + yaml.safe_dump(rec, sort_keys=True) + "---\n" + body,
        encoding="utf-8",
    )
    second = _compile(root)

    assert second["active_projects"][0]["source_content_sha256"] == first_hash
    assert second["semantic_hash"] == first["semantic_hash"]
    assert lpp.semantic_json(second) == lpp.semantic_json(first)


def test_one_field_change_is_bounded(tmp_path):
    root = _store(tmp_path, [("ALPHA", "active", {})])
    first = _compile(root)
    path = root / "workstreams" / "WS-ALPHA.md"
    path.write_text(
        _record("ALPHA", "active", next_action="A different bounded action."),
        encoding="utf-8",
    )
    second = _compile(root)
    assert first["semantic_hash"] != second["semantic_hash"]
    before = first["active_projects"][0]
    after = second["active_projects"][0]
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {
        "next_action",
        "source_content_sha256",
        "managed_description_block",
    }


def test_unmerged_sibling_fixture_is_not_canonical(tmp_path):
    root = _store(tmp_path, [("MAIN", "active", {})])
    other = tmp_path / "branch-fixture" / "workstreams"
    other.mkdir(parents=True)
    (other / "WS-DRAFT.md").write_text(
        _record("DRAFT", "active"), encoding="utf-8"
    )
    plan = _compile(root)
    assert [row["workstream_key"] for row in plan["active_projects"]] == [
        "WS:MAIN"
    ]


def test_malformed_record_refuses_plan_with_frozen_failure_code(tmp_path):
    root = tmp_path / "agentos"
    (root / "workstreams").mkdir(parents=True)
    (root / "workstreams" / "WS-BAD.md").write_text("not frontmatter")
    with pytest.raises(lpp.PlanError) as exc:
        _compile(root)
    failure = exc.value.failures[0]
    assert failure["code"] == "malformed_workstream_record"
    assert failure["source_rule"] == "unparseable"


def test_duplicate_workstream_key_uses_frozen_failure_code(tmp_path):
    root = tmp_path / "agentos"
    (root / "workstreams").mkdir(parents=True)
    (root / "workstreams" / "WS-ALPHA.md").write_text(
        _record("ALPHA", "active"), encoding="utf-8"
    )
    (root / "workstreams" / "WS-BETA.md").write_text(
        _record("ALPHA", "active"), encoding="utf-8"
    )
    with pytest.raises(lpp.PlanError) as exc:
        _compile(root)
    assert "duplicate_workstream_key" in {
        failure["code"] for failure in exc.value.failures
    }


def test_unknown_status_uses_frozen_failure_code(tmp_path):
    root = _store(tmp_path, [("ALPHA", "mystery", {})])
    with pytest.raises(lpp.PlanError) as exc:
        _compile(root)
    assert "unknown_canonical_status" in {
        failure["code"] for failure in exc.value.failures
    }


def test_socket_disabled_runtime_still_compiles(tmp_path, monkeypatch):
    root = _store(tmp_path, [("ALPHA", "active", {})])

    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket, "socket", blocked)
    plan = _compile(root)
    assert plan["summary"]["active_projects"] == 1


def test_typed_gate_is_observed_not_inferred_and_missing_source_is_named(tmp_path):
    root = _store(
        tmp_path,
        [
            ("PLAIN", "active", {}),
            (
                "BLOCKED",
                "blocked",
                {"blocked_by": ["explicit source"]},
            ),
            (
                "REVIEW",
                "awaiting_review",
                {},
            ),
            (
                "CEO",
                "active",
                {
                    "needs_ceo": {
                        "question": "Choose A or B",
                        "recommendation": "Choose A",
                    }
                },
            ),
        ],
    )
    plan = _compile(root)
    rows = {row["workstream_key"]: row for row in plan["active_projects"]}
    assert rows["WS:PLAIN"]["gate_observation"] == {
        "typed_source": None,
        "projection": "not_inferred",
    }
    assert rows["WS:BLOCKED"]["gate_observation"]["typed_source"] == "blocked_by"
    assert rows["WS:CEO"]["gate_observation"]["typed_source"] == "needs_ceo"
    assert rows["WS:CEO"]["gate_observation"]["projection"] == "observation_only"
    typed_missing = {
        warning["workstream_key"]
        for warning in plan["warnings"]
        if warning["code"] == "typed_gate_source_missing"
    }
    assert typed_missing == {"WS:REVIEW"}


def test_exact_linear_snapshot_reports_missing_ambiguous_drift_and_extra(tmp_path):
    root = _store(tmp_path, [("A", "active", {}), ("B", "active", {})])
    snapshot = tmp_path / "linear.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema": "linear_portfolio_snapshot.v1",
                "projects": [
                    {"workstream_key": "WS:A", "name": "wrong"},
                    {"workstream_key": "WS:A", "name": "duplicate"},
                    {"workstream_key": "WS:EXTRA", "name": "extra"},
                ],
            }
        )
    )
    plan = lpp.compile_plan(root, programs=None, linear_snapshot_path=snapshot)[0]
    codes = [warning["code"] for warning in plan["warnings"]]
    assert "existing_project_binding_ambiguous" in codes
    assert "existing_project_binding_missing" in codes
    assert "would_deactivate_or_archive" in codes


def test_linear_snapshot_status_class_distinguishes_healthy_history_from_stale_live(tmp_path):
    root = _store(
        tmp_path,
        [
            ("ACTIVE", "active", {}),
            ("DONE", "done", {}),
            ("STALE", "done", {}),
        ],
    )
    snapshot = tmp_path / "linear.json"
    snapshot.write_text(
        json.dumps(
            {
                "schema": "linear_portfolio_snapshot.v1",
                "projects": [
                    {
                        "workstream_key": "WS:ACTIVE",
                        "name": "WS:ACTIVE — Active",
                        "status_class": "started",
                    },
                    {
                        "workstream_key": "WS:DONE",
                        "name": "WS:DONE — Done",
                        "status_class": "completed",
                    },
                    {
                        "workstream_key": "WS:STALE",
                        "name": "WS:STALE — Stale",
                        "status_class": "started",
                    },
                ],
            }
        )
    )
    plan = lpp.compile_plan(root, programs=None, linear_snapshot_path=snapshot)[0]
    lifecycle = [
        warning
        for warning in plan["warnings"]
        if warning["code"] == "project_lifecycle_drift"
    ]
    assert lifecycle == [
        {
            "code": "project_lifecycle_drift",
            "workstream_key": "WS:STALE",
            "current": "started",
            "desired": "completed",
            "canonical_status": "done",
        }
    ]
    assert not any(
        warning["workstream_key"] == "WS:DONE"
        for warning in plan["warnings"]
        if "workstream_key" in warning
        and warning["code"] in {"would_deactivate_or_archive", "project_lifecycle_drift"}
    )
