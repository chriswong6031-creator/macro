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
            ("BLOCKED", "blocked", {}),
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


def test_malformed_record_refuses_plan(tmp_path):
    root = tmp_path / "agentos"
    (root / "workstreams").mkdir(parents=True)
    (root / "workstreams" / "WS-BAD.md").write_text("not frontmatter")
    with pytest.raises(lpp.PlanError) as exc:
        _compile(root)
    assert exc.value.failures[0]["rule"] == "unparseable"


def test_socket_disabled_runtime_still_compiles(tmp_path, monkeypatch):
    root = _store(tmp_path, [("ALPHA", "active", {})])

    def blocked(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket, "socket", blocked)
    plan = _compile(root)
    assert plan["summary"]["active_projects"] == 1


def test_typed_gate_is_observed_not_inferred(tmp_path):
    root = _store(
        tmp_path,
        [
            ("PLAIN", "active", {}),
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
    assert rows["WS:CEO"]["gate_observation"]["typed_source"] == "needs_ceo"
    assert rows["WS:CEO"]["gate_observation"]["projection"] == "observation_only"


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
