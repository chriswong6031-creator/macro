"""Focused, hermetic tests for the three-repository advisory build map."""
from __future__ import annotations

import copy
import json
import stat
from datetime import datetime, timezone

import pytest

from scripts import build_project_active_build_map as project_map


def _source_snapshot() -> dict:
    return {
        "schema": "project_active_builds.source.v1",
        "collected_at": "2026-08-11T12:00:00+00:00",
        "merged_days": 14,
        "repositories": [
            {
                "repo": "mastermindx-market-intelligence/macro",
                "base_branch": "main",
                "base_sha": "a" * 40,
                "open_prs": [
                    {
                        "number": 10,
                        "title": "Macro lane | one",
                        "branch": "claude/macro-one",
                        "updated_at": "2026-08-11T11:00:00Z",
                        "draft": False,
                        "merge_state": "DIRTY",
                        "files": [
                            ".github/workflows/ci.yml",
                            "engine/one.py",
                        ],
                        "body": (
                            "Depends on terminal#20 and "
                            "https://github.com/mastermindx-market-intelligence/"
                            "Mastermind/pull/30\n"
                            "Related discussion: #999"
                        ),
                    },
                    {
                        "number": 11,
                        "title": "Macro lane two",
                        "branch": "claude/macro-two",
                        "updated_at": "2026-08-11T10:00:00Z",
                        "draft": True,
                        "merge_state": "CLEAN",
                        "files": [
                            ".github/workflows/ci.yml",
                            "engine/two.py",
                        ],
                        "body": "No dependency here; mentions #10 conversationally.",
                    },
                ],
                "recently_merged": [
                    {
                        "number": 9,
                        "title": "Earlier Macro lane",
                        "branch": "claude/macro-nine",
                        "merged_at": "2026-08-10T10:00:00Z",
                    }
                ],
            },
            {
                "repo": "mastermindx-market-intelligence/mastermind-terminal",
                "base_branch": "master",
                "base_sha": "b" * 40,
                "open_prs": [
                    {
                        "number": 20,
                        "title": "Terminal lane",
                        "branch": "claude/terminal-lane",
                        "updated_at": "2026-08-11T09:00:00Z",
                        "draft": False,
                        "merge_state": "CLEAN",
                        # The same spelling in another repository is not a collision.
                        "files": [".github/workflows/ci.yml"],
                        "body": "",
                    }
                ],
                "recently_merged": [],
            },
            {
                "repo": "mastermindx-market-intelligence/Mastermind",
                "base_branch": "master",
                "base_sha": "c" * 40,
                "open_prs": [],
                "recently_merged": [
                    {
                        "number": 30,
                        "title": "Mastermind contract",
                        "branch": "claude/mastermind-contract",
                        "merged_at": "2026-08-11T08:00:00Z",
                    }
                ],
            },
        ],
    }


def test_repository_boundary_is_exactly_the_three_system_repositories():
    assert [
        (spec.repository, spec.base_branch) for spec in project_map.REPOSITORIES
    ] == [
        ("mastermindx-market-intelligence/macro", "main"),
        ("mastermindx-market-intelligence/mastermind-terminal", "master"),
        ("mastermindx-market-intelligence/Mastermind", "master"),
    ]


def test_compile_snapshot_populates_required_fields_and_dependency_statuses():
    payload = project_map.compile_snapshot(_source_snapshot())

    assert payload["schema"] == "project_active_builds.v1"
    assert payload["advisory_only"] is True
    assert payload["gates"] == []
    assert payload["summary"]["repository_count"] == 3
    assert payload["summary"]["open_prs"] == 3
    assert payload["summary"]["conflicts"] == 1

    macro_pr = payload["repositories"][0]["open_prs"][0]
    assert macro_pr["number"] == 10
    assert macro_pr["repo"] == "mastermindx-market-intelligence/macro"
    assert macro_pr["title"] == "Macro lane | one"
    assert macro_pr["branch"] == "claude/macro-one"
    assert macro_pr["updated_at"] == "2026-08-11T11:00:00Z"
    assert macro_pr["draft"] is False
    assert macro_pr["conflict"] is True
    assert macro_pr["protected_paths"] == [".github/workflows/ci.yml"]
    assert macro_pr["dependencies"] == [
        {
            "repo": "mastermindx-market-intelligence/mastermind-terminal",
            "pr": 20,
            "source": "pr_body",
            "status": "open",
        },
        {
            "repo": "mastermindx-market-intelligence/Mastermind",
            "pr": 30,
            "source": "pr_body",
            "status": "recently_merged",
        },
    ]


def test_file_collisions_are_same_repository_only_and_protected():
    payload = project_map.compile_snapshot(_source_snapshot())
    assert payload["file_collisions"] == [
        {
            "repo": "mastermindx-market-intelligence/macro",
            "pr_a": 10,
            "pr_b": 11,
            "shared_count": 1,
            "shared_files": [".github/workflows/ci.yml"],
            "protected_collision": True,
        }
    ]


def test_dependency_parser_ignores_non_dependency_mentions_and_external_repos():
    body = """Related: #77
Depends on macro#12 and owner/outside#5.
Blocked by https://github.com/mastermindx-market-intelligence/Mastermind/pull/15.
Requires #13.
"""
    assert project_map.extract_dependencies(
        body, "mastermindx-market-intelligence/mastermind-terminal"
    ) == [
        {
            "repo": "mastermindx-market-intelligence/macro",
            "pr": 12,
            "source": "pr_body",
        },
        {
            "repo": "mastermindx-market-intelligence/mastermind-terminal",
            "pr": 13,
            "source": "pr_body",
        },
        {
            "repo": "mastermindx-market-intelligence/Mastermind",
            "pr": 15,
            "source": "pr_body",
        },
    ]


def test_supplied_snapshot_render_is_deterministic_and_has_no_clock_access(monkeypatch):
    source = _source_snapshot()
    reordered = copy.deepcopy(source)
    reordered["repositories"].reverse()
    for repository in reordered["repositories"]:
        repository["open_prs"].reverse()
        repository["recently_merged"].reverse()

    class ForbiddenDateTime:
        @classmethod
        def now(cls, *_args, **_kwargs):
            raise AssertionError("rendering consulted the clock")

    monkeypatch.setattr(project_map, "datetime", ForbiddenDateTime)
    payload_a = project_map.compile_snapshot(source)
    payload_b = project_map.compile_snapshot(reordered)
    assert payload_a == payload_b
    assert project_map.render_markdown(payload_a) == project_map.render_markdown(payload_b)
    assert json.dumps(payload_a, sort_keys=True) == json.dumps(payload_b, sort_keys=True)


def test_markdown_is_explicitly_advisory_and_covers_all_sections():
    markdown = project_map.render_markdown(project_map.compile_snapshot(_source_snapshot()))
    assert "# Project Active Build Map" in markdown
    assert "## Repositories" in markdown
    assert "## Open Pull Requests" in markdown
    assert "## File Collisions" in markdown
    assert "## Recently Merged" in markdown
    assert "**Advisory only.**" in markdown
    assert "no CI, merge, deploy" in markdown
    assert "Macro lane \\| one" in markdown


def test_markdown_discloses_truncated_file_and_collision_coverage():
    source = _source_snapshot()
    source["repositories"][0]["open_prs"][0]["files_truncated"] = True
    markdown = project_map.render_markdown(project_map.compile_snapshot(source))
    assert "2+ (truncated)" in markdown
    assert "**Incomplete file census:**" in markdown
    assert "collision negatives are indeterminate" in markdown
    assert "Collision coverage is incomplete" in markdown


def test_markdown_discloses_truncated_open_pr_census():
    source = _source_snapshot()
    source["repositories"][1]["open_prs_truncated"] = True
    markdown = project_map.render_markdown(project_map.compile_snapshot(source))
    assert "**Incomplete PR census:**" in markdown
    assert "Open counts, protected-path counts, dependencies" in markdown
    assert "collision negatives are indeterminate" in markdown


def test_missing_or_extra_repository_is_rejected():
    missing = _source_snapshot()
    missing["repositories"] = missing["repositories"][:-1]
    with pytest.raises(ValueError, match="exactly macro/main"):
        project_map.compile_snapshot(missing)

    extra = _source_snapshot()
    extra["repositories"].append(
        {"repo": "owner/fourth", "base_branch": "main", "open_prs": [], "recently_merged": []}
    )
    with pytest.raises(ValueError, match="exactly macro/main"):
        project_map.compile_snapshot(extra)


def test_unknown_snapshot_schema_is_rejected():
    snapshot = _source_snapshot()
    snapshot["schema"] = "project_active_builds.future"
    with pytest.raises(ValueError, match="snapshot.schema"):
        project_map.compile_snapshot(snapshot)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("collected_at", "not-a-time", "UTC timestamp"),
        ("collected_at", "2026-08-11T12:00:00-07:00", "must use UTC"),
        ("merged_days", 0, "integer from 1"),
        ("merged_days", 91, "integer from 1"),
    ],
)
def test_snapshot_provenance_is_strict(field, value, message):
    snapshot = _source_snapshot()
    snapshot[field] = value
    with pytest.raises(ValueError, match=message):
        project_map.compile_snapshot(snapshot)


def test_repository_sha_pr_numbers_and_paths_are_strict():
    bad_sha = _source_snapshot()
    bad_sha["repositories"][0]["base_sha"] = "wrong"
    with pytest.raises(ValueError, match="40-hex commit SHA"):
        project_map.compile_snapshot(bad_sha)

    duplicate_pr = _source_snapshot()
    duplicate_pr["repositories"][0]["open_prs"].append(
        copy.deepcopy(duplicate_pr["repositories"][0]["open_prs"][0])
    )
    with pytest.raises(ValueError, match="positive and unique"):
        project_map.compile_snapshot(duplicate_pr)

    bad_path = _source_snapshot()
    bad_path["repositories"][0]["open_prs"][0]["files"] = ["../escape.yml"]
    with pytest.raises(ValueError, match="repository-relative path"):
        project_map.compile_snapshot(bad_path)

    contradictory_state = _source_snapshot()
    contradictory_state["repositories"][0]["recently_merged"][0]["number"] = 10
    with pytest.raises(ValueError, match="both open and merged state"):
        project_map.compile_snapshot(contradictory_state)


def test_network_failure_never_clobbers_existing_outputs(tmp_path, monkeypatch):
    json_out = tmp_path / "project.json"
    md_out = tmp_path / "project.md"
    json_out.write_text("prior-json", encoding="utf-8")
    md_out.write_text("prior-markdown", encoding="utf-8")
    monkeypatch.setattr(project_map, "collect_source_snapshot", lambda **_kwargs: None)

    assert project_map.main(
        ["--json-out", str(json_out), "--md-out", str(md_out)]
    ) == 0
    assert json_out.read_text(encoding="utf-8") == "prior-json"
    assert md_out.read_text(encoding="utf-8") == "prior-markdown"


def test_snapshot_input_is_hermetic_and_writes_both_outputs(tmp_path, monkeypatch):
    snapshot_in = tmp_path / "source.json"
    json_out = tmp_path / "project.json"
    md_out = tmp_path / "project.md"
    snapshot_in.write_text(json.dumps(_source_snapshot()), encoding="utf-8")

    def no_network(_args):
        raise AssertionError("snapshot mode attempted GitHub access")

    monkeypatch.setattr(project_map, "_run_gh", no_network)
    assert project_map.main(
        [
            "--snapshot-in",
            str(snapshot_in),
            "--json-out",
            str(json_out),
            "--md-out",
            str(md_out),
        ]
    ) == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["collected_at"] == "2026-08-11T12:00:00+00:00"
    assert payload["summary"]["repository_count"] == 3
    assert "Project Active Build Map" in md_out.read_text(encoding="utf-8")
    assert stat.S_IMODE(json_out.stat().st_mode) == 0o644
    assert stat.S_IMODE(md_out.stat().st_mode) == 0o644


def test_output_pair_rolls_back_if_second_publish_fails(tmp_path, monkeypatch):
    snapshot_in = tmp_path / "source.json"
    json_out = tmp_path / "project.json"
    md_out = tmp_path / "project.md"
    snapshot_in.write_text(json.dumps(_source_snapshot()), encoding="utf-8")
    json_out.write_text("prior-json", encoding="utf-8")
    md_out.write_text("prior-markdown", encoding="utf-8")

    real_replace = project_map.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second-output failure")
        return real_replace(source, destination)

    monkeypatch.setattr(project_map.os, "replace", fail_second_replace)
    assert project_map.main(
        [
            "--snapshot-in",
            str(snapshot_in),
            "--json-out",
            str(json_out),
            "--md-out",
            str(md_out),
        ]
    ) == 2
    assert json_out.read_text(encoding="utf-8") == "prior-json"
    assert md_out.read_text(encoding="utf-8") == "prior-markdown"


def test_output_pair_preserves_backup_if_rollback_itself_fails(tmp_path, monkeypatch):
    snapshot_in = tmp_path / "source.json"
    json_out = tmp_path / "project.json"
    md_out = tmp_path / "project.md"
    snapshot_in.write_text(json.dumps(_source_snapshot()), encoding="utf-8")
    json_out.write_text("prior-json", encoding="utf-8")
    md_out.write_text("prior-markdown", encoding="utf-8")

    real_replace = project_map.os.replace
    calls = 0

    def fail_publish_and_restore(source, destination):
        nonlocal calls
        calls += 1
        if calls in {2, 3}:
            raise OSError(f"injected replace failure {calls}")
        return real_replace(source, destination)

    monkeypatch.setattr(project_map.os, "replace", fail_publish_and_restore)
    assert project_map.main(
        [
            "--snapshot-in",
            str(snapshot_in),
            "--json-out",
            str(json_out),
            "--md-out",
            str(md_out),
        ]
    ) == 2
    preserved = list(tmp_path.glob(".project.json.backup.*"))
    assert len(preserved) == 1
    assert preserved[0].read_text(encoding="utf-8") == "prior-json"
    assert md_out.read_text(encoding="utf-8") == "prior-markdown"


def test_live_collection_queries_every_declared_repository_and_branch():
    calls: list[list[str]] = []

    def fake_gh(args: list[str]):
        calls.append(args)
        if args[0] == "api":
            return {"object": {"sha": args[1].split("/")[-1] * 40}}
        if args[:2] == ["pr", "list"] and "open" in args:
            return []
        if args[:2] == ["pr", "list"] and "merged" in args:
            return []
        raise AssertionError(f"unexpected gh call: {args}")

    snapshot = project_map.collect_source_snapshot(
        collected_at=datetime(2026, 8, 11, 12, tzinfo=timezone.utc),
        gh_runner=fake_gh,
    )
    assert snapshot is not None
    assert [repository["repo"] for repository in snapshot["repositories"]] == [
        spec.repository for spec in project_map.REPOSITORIES
    ]
    api_calls = [args for args in calls if args[0] == "api"]
    assert api_calls == [
        ["api", "repos/mastermindx-market-intelligence/macro/git/ref/heads/main"],
        [
            "api",
            "repos/mastermindx-market-intelligence/mastermind-terminal/git/ref/heads/master",
        ],
        ["api", "repos/mastermindx-market-intelligence/Mastermind/git/ref/heads/master"],
    ]


def test_live_collection_aborts_the_whole_snapshot_on_one_repository_failure():
    def fake_gh(args: list[str]):
        if "mastermind-terminal" in " ".join(args):
            return None
        if args[0] == "api":
            return {"object": {"sha": "a" * 40}}
        return []

    assert project_map.collect_source_snapshot(gh_runner=fake_gh) is None
