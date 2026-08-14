"""Trusted-base CI authority gate and workflow security contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import ci_authority as AUTHORITY
from scripts.check_self_mod_fence import IMMUTABLE_PATTERNS
from scripts.ci_authority_paths import (
    AuthorityPathError,
    CI_AUTHORITY_PATTERNS,
    canonical_repo_path,
    is_ci_authority_path,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci-authority.yml"
REPOSITORY = "mastermindx-market-intelligence/macro"
PR_NUMBER = 5588
HEAD = "a" * 40
NEW_HEAD = "b" * 40
BASE = "c" * 40


def _event(
    *,
    head_repository: str = REPOSITORY,
    author: str = "operator",
    actor: str | None = None,
) -> dict:
    sender = author if actor is None else actor
    return {
        "action": "synchronize",
        "repository": {"full_name": REPOSITORY, "default_branch": "main"},
        "sender": {"login": sender},
        "pull_request": {
            "number": PR_NUMBER,
            "head": {"sha": HEAD, "repo": {"full_name": head_repository}},
            "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
            "user": {"login": author},
        },
    }


def _pull(
    files: list[dict[str, object]],
    *,
    head: str = HEAD,
    head_repository: str = REPOSITORY,
    author: str = "operator",
) -> dict:
    return {
        "number": PR_NUMBER,
        "state": "open",
        "changed_files": len(files),
        "base": {"repo": {"full_name": REPOSITORY}},
        "head": {"sha": head, "repo": {"full_name": head_repository}},
        "user": {"login": author},
    }


class FakeApi:
    def __init__(
        self,
        files: list[dict[str, object]],
        *,
        head: str = HEAD,
        head_repository: str = REPOSITORY,
        author: str = "operator",
        permission: str = "admin",
        permissions: dict[str, str] | None = None,
        fail: str = "",
    ) -> None:
        self.files = files
        self.pull = _pull(
            files,
            head=head,
            head_repository=head_repository,
            author=author,
        )
        self.author = author
        self.permission = permission
        self.permissions = permissions or {}
        self.fail = fail
        self.calls: list[tuple[Any, ...]] = []
        self.checks: list[dict[str, object]] = []

    def get_pull(self, repository: str, number: int) -> object:
        self.calls.append(("pull", repository, number))
        if self.fail == "pull":
            raise RuntimeError("private API response")
        return self.pull

    def list_pull_files(
        self, repository: str, number: int, expected_count: int
    ) -> object:
        self.calls.append(("files", repository, number, expected_count))
        if self.fail == "files":
            raise RuntimeError("private API response")
        return self.files

    def get_collaborator_permission(self, repository: str, login: str) -> object:
        self.calls.append(("permission", repository, login))
        if self.fail == "permission":
            raise RuntimeError("private API response")
        return {
            "permission": self.permissions.get(login, self.permission),
            "user": {"login": login},
        }

    def create_check(self, repository: str, payload: dict[str, object]) -> object:
        self.calls.append(("check", repository))
        if self.fail == "check":
            raise RuntimeError("private API response")
        self.checks.append(payload)
        return {"id": 123, "app": {"id": 15368}}


def _file(path: str, *, previous: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {"filename": path, "status": "modified"}
    if previous is not None:
        result["previous_filename"] = previous
        result["status"] = "renamed"
    return result


def test_fork_authority_change_fails_and_publishes_failure_on_exact_head() -> None:
    fork = "contributor/macro"
    api = FakeApi(
        [_file(".github/workflows/ci.yml")],
        head_repository=fork,
        author="contributor",
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(head_repository=fork, author="contributor"), REPOSITORY, api
    )

    assert code == 1
    assert decision["reason"] == "fork_cannot_change_ci_authority"
    assert decision["authority_hits"] == [".github/workflows/ci.yml"]
    assert not any(call[0] == "permission" for call in api.calls)
    assert check["head_sha"] == HEAD
    assert check["conclusion"] == "failure"
    assert api.checks == [check]


@pytest.mark.parametrize("shadow", ["scripts/argparse.py", "scripts/yaml.py"])
def test_fork_cannot_add_python_import_shadow_that_self_greens_ci(shadow: str) -> None:
    fork = "contributor/macro"
    api = FakeApi(
        [_file(shadow)],
        head_repository=fork,
        author="contributor",
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(head_repository=fork, author="contributor"), REPOSITORY, api
    )
    assert code == 1
    assert decision["reason"] == "fork_cannot_change_ci_authority"
    assert decision["authority_hits"] == [shadow]
    assert check["conclusion"] == "failure"


def test_ordinary_fork_change_passes_without_an_authority_query() -> None:
    fork = "contributor/macro"
    api = FakeApi(
        [_file("docs/ordinary-note.md")],
        head_repository=fork,
        author="contributor",
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(head_repository=fork, author="contributor"), REPOSITORY, api
    )

    assert code == 0
    assert decision["reason"] == "ordinary_change"
    assert decision["authority_hit_count"] == 0
    assert check["conclusion"] == "success"
    assert not any(call[0] == "permission" for call in api.calls)


def test_same_repo_non_admin_authority_change_fails() -> None:
    api = FakeApi([_file("scripts/run_ci_pack.py")], permission="write")
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )

    assert code == 1
    assert decision["reason"] == "same_repo_author_is_not_admin"
    assert decision["admin_verified"] is False
    assert check["conclusion"] == "failure"


def test_same_repo_admin_authority_change_passes() -> None:
    api = FakeApi([_file("scripts/ci_structural_preflight.py")], permission="admin")
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api, details_url="https://github.com/o/r/actions/runs/9"
    )

    assert code == 0
    assert decision["reason"] == "same_repo_admin_authority_change"
    assert decision["author_admin_verified"] is True
    assert decision["actor_admin_verified"] is True
    assert decision["admin_verified"] is True
    assert check["conclusion"] == "success"
    assert check["details_url"] == "https://github.com/o/r/actions/runs/9"


def test_admin_authored_pr_with_non_admin_synchronize_sender_is_rejected() -> None:
    api = FakeApi(
        [_file("scripts/run_ci_pack.py")],
        author="operator",
        permissions={"operator": "admin", "collaborator": "write"},
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(author="operator", actor="collaborator"), REPOSITORY, api
    )

    assert code == 1
    assert decision["author"] == "operator"
    assert decision["actor"] == "collaborator"
    assert decision["author_admin_verified"] is True
    assert decision["actor_admin_verified"] is False
    assert decision["admin_verified"] is False
    assert decision["reason"] == "current_head_actor_is_not_admin"
    assert check["conclusion"] == "failure"
    assert [call for call in api.calls if call[0] == "permission"] == [
        ("permission", REPOSITORY, "operator"),
        ("permission", REPOSITORY, "collaborator"),
    ]


def test_admin_authored_pr_with_admin_synchronize_sender_passes() -> None:
    api = FakeApi(
        [_file("scripts/run_ci_pack.py")],
        author="operator",
        permissions={"operator": "admin", "release-admin": "admin"},
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(author="operator", actor="release-admin"), REPOSITORY, api
    )

    assert code == 0
    assert decision["author_admin_verified"] is True
    assert decision["actor_admin_verified"] is True
    assert decision["admin_verified"] is True
    assert decision["reason"] == "same_repo_admin_authority_change"
    assert check["conclusion"] == "success"


def test_stale_event_head_fails_closed_before_files_or_permission() -> None:
    api = FakeApi([_file("docs/readme.md")], head=NEW_HEAD)
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )

    assert code == 1
    assert decision["reason"] == "event_head_or_author_drift"
    assert check["head_sha"] == HEAD
    assert [call[0] for call in api.calls] == ["pull", "check"]


def test_head_changing_during_file_pagination_fails_closed() -> None:
    class RacingApi(FakeApi):
        def get_pull(self, repository: str, number: int) -> object:
            response = super().get_pull(repository, number)
            if sum(call[0] == "pull" for call in self.calls) == 2:
                return _pull(self.files, head=NEW_HEAD)
            return response

    api = RacingApi([_file("docs/readme.md")])
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )
    assert code == 1
    assert decision["reason"] == "event_head_or_files_drift"
    assert check["head_sha"] == HEAD
    assert [call[0] for call in api.calls] == ["pull", "files", "pull", "check"]


@pytest.mark.parametrize(
    "failure,reason",
    [
        ("pull", "current_pull_api_unavailable"),
        ("files", "changed_files_api_unavailable"),
        ("permission", "author_admin_permission_api_unavailable"),
    ],
)
def test_read_api_failure_is_red_but_still_gets_a_terminal_check(
    failure: str, reason: str
) -> None:
    api = FakeApi([_file("scripts/run_ci_pack.py")], fail=failure)
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )

    assert code == 1
    assert decision["reason"] == reason
    assert check["status"] == "completed"
    assert check["conclusion"] == "failure"
    assert api.checks == [check]


def test_check_creation_failure_is_a_controller_error() -> None:
    api = FakeApi([_file("docs/readme.md")], fail="check")
    with pytest.raises(AUTHORITY.GitHubApiError, match="could not be created"):
        AUTHORITY.run_pull_request_target(_event(), REPOSITORY, api)


def test_exact_check_payload_binds_name_head_verdict_and_provenance() -> None:
    api = FakeApi([_file("docs/readme.md")])
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )

    assert code == 0
    assert check == {
        "name": "ci-authority",
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "external_id": f"ci.authority.v1:{REPOSITORY}:{PR_NUMBER}:{HEAD}",
        "output": {
            "title": "CI authority accepted",
            "summary": json.dumps(
                decision, ensure_ascii=True, separators=(",", ":")
            ),
        },
    }


def test_renaming_authority_away_is_still_an_authority_change() -> None:
    api = FakeApi(
        [_file("docs/ordinary.py", previous="scripts/run_ci_pack.py")],
        permission="write",
    )
    code, decision, _check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )
    assert code == 1
    assert decision["authority_hits"] == ["scripts/run_ci_pack.py"]


def test_rename_without_previous_name_is_rejected_not_treated_as_ordinary() -> None:
    malformed = _file("scripts/ordinary.py")
    malformed["status"] = "renamed"
    api = FakeApi([malformed])
    code, decision, _check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )
    assert code == 1
    assert decision["reason"] == "changed_files_rejected"


@pytest.mark.parametrize(
    "path",
    [
        "/scripts/run_ci_pack.py",
        "./scripts/run_ci_pack.py",
        "scripts//run_ci_pack.py",
        "scripts/../scripts/run_ci_pack.py",
        "scripts\\run_ci_pack.py",
        "scripts/run_ci_pack.py\nforged",
        "scripts/\u202egreen.py",
    ],
)
def test_noncanonical_or_control_unsafe_api_paths_fail_closed(path: str) -> None:
    with pytest.raises(AuthorityPathError):
        canonical_repo_path(path)
    api = FakeApi([_file(path)])
    code, decision, _check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )
    assert code == 1
    assert decision["reason"] == "changed_files_rejected"


def test_pull_files_client_paginates_and_requires_the_exact_current_count() -> None:
    class PagingApi(AUTHORITY.GitHubApi):
        def __init__(self) -> None:
            super().__init__("https://api.github.test", "token")
            self.paths: list[str] = []

        def _request_json(self, method, path, *, payload=None, expected_status):
            self.paths.append(path)
            page = int(path.rsplit("=", 1)[1])
            count = 100 if page == 1 else 1
            return [_file(f"docs/{page}-{index}.md") for index in range(count)]

    api = PagingApi()
    result = api.list_pull_files(REPOSITORY, PR_NUMBER, 101)
    assert len(result) == 101
    assert api.paths == [
        f"/repos/mastermindx-market-intelligence/macro/pulls/{PR_NUMBER}/files?per_page=100&page=1",
        f"/repos/mastermindx-market-intelligence/macro/pulls/{PR_NUMBER}/files?per_page=100&page=2",
    ]


def test_shared_ci_authority_inventory_cannot_drift_from_self_mod_fence() -> None:
    required = {
        ".github/ci/**",
        ".github/workflows/**",
        "scripts/**",
    }
    assert required <= set(CI_AUTHORITY_PATTERNS)
    assert len(CI_AUTHORITY_PATTERNS) == len(set(CI_AUTHORITY_PATTERNS))
    assert set(CI_AUTHORITY_PATTERNS) <= set(IMMUTABLE_PATTERNS)
    assert is_ci_authority_path(".github/ci/legacy-jobs.yml")
    assert is_ci_authority_path(".github/ci/scope-index.json")
    for path in (
        "scripts/run_ci_pack.py",
        "scripts/ci_structural_preflight.py",
        "scripts/ci_committed_scope_index.py",
        "scripts/ci_scope_dependencies.py",
        "scripts/audit_unrun_tests.py",
        "scripts/ci_failure_summary.py",
        "scripts/ci_cancelled_run_completion.py",
        "scripts/check_self_mod_fence.py",
        "scripts/argparse.py",
        "scripts/yaml.py",
    ):
        assert is_ci_authority_path(path), path
    assert not is_ci_authority_path("docs/ordinary-note.md")


def test_merge_group_envelope_produces_stable_trusted_verdict() -> None:
    event = {
        "action": "checks_requested",
        "repository": {"full_name": REPOSITORY},
        "merge_group": {"head_sha": HEAD, "base_sha": BASE},
    }
    assert AUTHORITY.evaluate_merge_group(event, REPOSITORY) == {
        "schema": AUTHORITY.SCHEMA,
        "event": "merge_group",
        "repository": REPOSITORY,
        "head_sha": HEAD,
        "base_sha": BASE,
        "allowed": True,
        "reason": "trusted_default_branch_merge_group",
    }


def test_workflow_is_required_workflow_shaped_and_never_executes_candidate() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(source)
    job = document["jobs"]["ci-authority"]
    checkout, pull_step, merge_group_step = job["steps"]

    assert re.search(r"^  pull_request_target:\s*$", source, re.MULTILINE)
    assert not re.search(r"^  pull_request:\s*$", source, re.MULTILINE)
    assert "types: [opened, synchronize, reopened]" in source
    assert re.search(r"^  merge_group:\s*$", source, re.MULTILINE)
    assert "types: [checks_requested]" in source
    assert document["permissions"] == {}
    assert job["name"] == "ci-authority"
    assert job["permissions"] == {
        "checks": "write",
        "contents": "read",
        "pull-requests": "read",
    }
    assert checkout["uses"] == (
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
    )
    assert checkout["with"] == {
        "ref": "${{ github.event.repository.default_branch }}",
        "fetch-depth": 1,
        "sparse-checkout": "scripts",
        "persist-credentials": False,
    }
    assert "pull_request.head" not in json.dumps(checkout)
    assert "merge_group.head" not in json.dumps(checkout)
    assert "github.sha" not in json.dumps(checkout)
    assert pull_step["if"] == "${{ github.event_name == 'pull_request_target' }}"
    assert merge_group_step["if"] == "${{ github.event_name == 'merge_group' }}"
    assert pull_step["run"] == merge_group_step["run"]
    assert pull_step["run"].startswith("python3 scripts/ci_authority.py")
    assert "subprocess" not in (ROOT / "scripts/ci_authority.py").read_text()
