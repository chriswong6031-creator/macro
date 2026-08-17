"""Trusted-base CI authority gate and workflow security contracts."""

from __future__ import annotations

import io
import json
import re
import time
import urllib.error
import urllib.request
from email.message import Message
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
OTHER_BASE = "d" * 40
BASE_REF = "main"


def _event(
    *,
    head_repository: str = REPOSITORY,
    author: str = "operator",
    actor: str | None = None,
    base_sha: str = BASE,
    base_ref: str = BASE_REF,
) -> dict:
    sender = author if actor is None else actor
    return {
        "action": "synchronize",
        "repository": {"full_name": REPOSITORY, "default_branch": "main"},
        "sender": {"login": sender},
        "pull_request": {
            "number": PR_NUMBER,
            "head": {"sha": HEAD, "repo": {"full_name": head_repository}},
            "base": {
                "sha": base_sha,
                "ref": base_ref,
                "repo": {"full_name": REPOSITORY},
            },
            "user": {"login": author},
        },
    }


def _pull(
    files: list[dict[str, object]],
    *,
    head: str = HEAD,
    head_repository: str = REPOSITORY,
    author: str = "operator",
    base_sha: str = BASE,
    base_ref: str = BASE_REF,
) -> dict:
    return {
        "number": PR_NUMBER,
        "state": "open",
        "changed_files": len(files),
        "base": {
            "sha": base_sha,
            "ref": base_ref,
            "repo": {"full_name": REPOSITORY},
        },
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
        base_sha: str = BASE,
        base_ref: str = BASE_REF,
        fail: str = "",
    ) -> None:
        self.files = files
        self.pull = _pull(
            files,
            head=head,
            head_repository=head_repository,
            author=author,
            base_sha=base_sha,
            base_ref=base_ref,
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
    assert [item["name"] for item in api.checks] == [
        "ci-authority/codex/merge-queue-pilot",
        "ci-authority/main",
    ]
    assert api.checks[-1] == check
    assert all(item["conclusion"] == "failure" for item in api.checks)


@pytest.mark.parametrize(
    "shadow",
    [
        "scripts/argparse.py",
        "scripts/yaml.py",
        "shlex.py",
        "yaml/__init__.py",
        "json.py",
    ],
)
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


@pytest.mark.parametrize(
    "control_path",
    [
        "tests/conftest.py",
        "pyproject.toml",
        "requirements-ci.txt",
        "package.json",
        "sitecustomize.py",
    ],
)
def test_fork_cannot_change_test_runtime_control(control_path: str) -> None:
    fork = "contributor/macro"
    api = FakeApi(
        [_file(control_path)],
        head_repository=fork,
        author="contributor",
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(head_repository=fork, author="contributor"), REPOSITORY, api
    )
    assert code == 1
    assert decision["reason"] == "fork_cannot_change_ci_authority"
    assert decision["authority_hits"] == [control_path]
    assert check["conclusion"] == "failure"


@pytest.mark.parametrize(
    "ordinary_path",
    [
        "docs/ordinary-note.md",
        "engine/json.py",
        "engine/yaml/__init__.py",
    ],
)
def test_ordinary_fork_change_passes_without_an_authority_query(
    ordinary_path: str,
) -> None:
    fork = "contributor/macro"
    api = FakeApi(
        [_file(ordinary_path)],
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


def test_edited_event_rechecks_the_same_head_and_base_identity() -> None:
    event = _event()
    event["action"] = "edited"
    api = FakeApi([_file("docs/ordinary-note.md")])
    code, decision, check = AUTHORITY.run_pull_request_target(
        event, REPOSITORY, api
    )

    assert code == 0
    assert decision["event_action"] == "edited"
    assert decision["head_sha"] == HEAD
    assert decision["base_sha"] == BASE
    assert decision["base_ref"] == BASE_REF
    assert check["conclusion"] == "success"


def test_main_and_pilot_retargets_invalidate_the_old_context_on_reused_head() -> None:
    files = [_file("docs/ordinary-note.md")]
    api = FakeApi(files)

    main_event = _event()
    main_event["action"] = "edited"
    code, _decision, check = AUTHORITY.run_pull_request_target(
        main_event, REPOSITORY, api
    )
    assert code == 0
    assert check["name"] == "ci-authority/main"

    api.pull = _pull(
        files,
        base_sha=OTHER_BASE,
        base_ref="codex/merge-queue-pilot",
    )
    pilot_event = _event(
        base_sha=OTHER_BASE,
        base_ref="codex/merge-queue-pilot",
    )
    pilot_event["action"] = "edited"
    code, _decision, check = AUTHORITY.run_pull_request_target(
        pilot_event, REPOSITORY, api
    )
    assert code == 0
    assert check["name"] == "ci-authority/codex/merge-queue-pilot"

    api.pull = _pull(files)
    code, _decision, check = AUTHORITY.run_pull_request_target(
        main_event, REPOSITORY, api
    )
    assert code == 0
    assert check["name"] == "ci-authority/main"

    assert [
        (item["name"], item["conclusion"])
        for item in api.checks
    ] == [
        ("ci-authority/codex/merge-queue-pilot", "failure"),
        ("ci-authority/main", "success"),
        ("ci-authority/main", "failure"),
        ("ci-authority/codex/merge-queue-pilot", "success"),
        ("ci-authority/codex/merge-queue-pilot", "failure"),
        ("ci-authority/main", "success"),
    ]


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
    assert decision["reason"] == "event_head_base_or_author_drift"
    assert check["head_sha"] == HEAD
    assert [call[0] for call in api.calls] == ["pull", "check", "check"]


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
    assert decision["reason"] == "event_head_base_or_files_drift"
    assert check["head_sha"] == HEAD
    assert [call[0] for call in api.calls] == [
        "pull", "files", "pull", "check", "check"
    ]


def test_base_retarget_with_reused_head_fails_before_files() -> None:
    api = FakeApi(
        [_file("docs/readme.md")],
        base_sha=OTHER_BASE,
        base_ref="codex/merge-queue-pilot",
    )
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )

    assert code == 1
    assert decision["head_sha"] == HEAD
    assert decision["base_sha"] == BASE
    assert decision["base_ref"] == BASE_REF
    assert decision["reason"] == "event_head_base_or_author_drift"
    assert check["conclusion"] == "failure"
    assert [call[0] for call in api.calls] == ["pull", "check", "check"]


def test_reused_head_cannot_hide_base_drift_during_files_query() -> None:
    class BaseRacingApi(FakeApi):
        def get_pull(self, repository: str, number: int) -> object:
            response = super().get_pull(repository, number)
            if sum(call[0] == "pull" for call in self.calls) == 2:
                return _pull(
                    self.files,
                    head=HEAD,
                    base_sha=OTHER_BASE,
                    base_ref="codex/merge-queue-pilot",
                )
            return response

    api = BaseRacingApi([_file("docs/readme.md")])
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )
    assert code == 1
    assert decision["head_sha"] == HEAD
    assert decision["reason"] == "event_head_base_or_files_drift"
    assert check["conclusion"] == "failure"
    assert [call[0] for call in api.calls] == [
        "pull", "files", "pull", "check", "check"
    ]


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
    assert api.checks[-1] == check
    assert len(api.checks) == 2
    assert all(item["conclusion"] == "failure" for item in api.checks)


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
    receipt = dict(decision)
    receipt.update(
        {
            "check_context": "ci-authority/main",
            "context_base_ref": "main",
            "context_active": True,
            "context_allowed": True,
            "context_reason": "ordinary_change",
        }
    )
    assert check == {
        "name": "ci-authority/main",
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        "external_id": (
            f"ci.authority.v1:{REPOSITORY}:{PR_NUMBER}:{HEAD}:main"
        ),
        "output": {
            "title": "CI authority context accepted",
            "summary": json.dumps(
                receipt, ensure_ascii=True, separators=(",", ":")
            ),
        },
    }
    assert api.checks[0]["name"] == "ci-authority/codex/merge-queue-pilot"
    assert api.checks[0]["conclusion"] == "failure"


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
        "/".join(("scripts", "", "run_ci_pack.py")),
        "/".join(("scripts", "..", "scripts", "run_ci_pack.py")),
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
        ".claude/hooks/**",
        ".github/ci/**",
        ".github/workflows/**",
        "scripts/**",
        "*.py",
        "*/__init__.py",
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
        "shlex.py",
        "yaml/__init__.py",
        "json.py",
        "tests/conftest.py",
        "pyproject.toml",
        "requirements-ci.txt",
        "package.json",
        "sitecustomize.py",
    ):
        assert is_ci_authority_path(path), path
    assert not is_ci_authority_path("docs/ordinary-note.md")
    assert not is_ci_authority_path("engine/json.py")
    assert not is_ci_authority_path("engine/yaml/__init__.py")


def test_merge_group_envelope_produces_stable_trusted_verdict() -> None:
    event = {
        "action": "checks_requested",
        "repository": {"full_name": REPOSITORY},
        "merge_group": {
            "head_sha": HEAD,
            "base_sha": BASE,
            "base_ref": "refs/heads/main",
        },
    }
    assert AUTHORITY.evaluate_merge_group(event, REPOSITORY) == {
        "schema": AUTHORITY.SCHEMA,
        "event": "merge_group",
        "repository": REPOSITORY,
        "head_sha": HEAD,
        "base_sha": BASE,
        "base_ref": "main",
        "base_repository": REPOSITORY,
        "allowed": True,
        "reason": "trusted_default_branch_merge_group",
    }


@pytest.mark.parametrize(
    "base_ref,base_sha,expected_name",
    [
        ("main", BASE, "ci-authority/main"),
        (
            "codex/merge-queue-pilot",
            OTHER_BASE,
            "ci-authority/codex/merge-queue-pilot",
        ),
    ],
)
def test_merge_group_publishes_matching_base_context_on_synthetic_head(
    base_ref: str, base_sha: str, expected_name: str
) -> None:
    event = {
        "action": "checks_requested",
        "repository": {"full_name": REPOSITORY},
        "merge_group": {
            "head_sha": HEAD,
            "base_sha": base_sha,
            "base_ref": f"refs/heads/{base_ref}",
        },
    }
    api = FakeApi([])
    code, decision, check = AUTHORITY.run_merge_group(event, REPOSITORY, api)

    assert code == 0
    assert decision["base_ref"] == base_ref
    assert check["name"] == expected_name
    assert check["head_sha"] == HEAD
    assert check["status"] == "completed"
    assert check["conclusion"] == "success"
    assert api.checks == [check]


def test_workflow_is_required_workflow_shaped_and_never_executes_candidate() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(source)
    job = document["jobs"]["ci-authority"]
    checkout, pull_step, merge_group_step = job["steps"]

    assert re.search(r"^  pull_request_target:\s*$", source, re.MULTILINE)
    assert not re.search(r"^  pull_request:\s*$", source, re.MULTILINE)
    assert "types: [opened, synchronize, reopened, edited]" in source
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
    assert merge_group_step["env"] == {
        "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"
    }
    assert pull_step["run"] == merge_group_step["run"]
    assert pull_step["run"].startswith("python3 scripts/ci_authority.py")
    assert "subprocess" not in (ROOT / "scripts/ci_authority.py").read_text()
    assert "diagnostic evidence only" in source
    assert "must never be the sole required authority" in source
    assert "required-workflow rule remains mandatory" in source
    assert "ci-authority/main" in source
    assert "ci-authority/codex/merge-queue-pilot" in source
    assert "metadata-only retarget seam" in source


# ---------------------------------------------------------------------------
# Bounded retry-with-backoff on the GitHubApi REST client.
#
# The fence failed closed fleet-wide on 2026-08-17 (~3h, 4 branches) because a
# single transient 504/429 killed a one-shot ``urlopen`` and a bare
# ``except Exception:`` discarded the exception, leaving one opaque reason
# string (``author_admin_permission_api_unavailable``) for every failure mode.
# These tests exercise the retry loop, the classification of failure modes,
# and the swallowed-exception annotation directly against ``GitHubApi`` via a
# scripted fake for ``urllib.request.urlopen`` — no real network calls.
# ---------------------------------------------------------------------------


class _FakeHttpResponse:
    """Minimal stand-in for the context manager ``urlopen`` returns on success."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self, _n: int = -1) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class _ScriptedUrlopen:
    """Monkeypatch target for ``urllib.request.urlopen`` with scripted outcomes.

    Each scripted outcome is either a ``(status, body)`` pair (success) or a
    ``BaseException`` instance to raise (transient or terminal failure).
    """

    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, request: object, timeout: float | None = None) -> _FakeHttpResponse:
        self.calls += 1
        if not self._outcomes:
            raise AssertionError("_ScriptedUrlopen ran out of scripted outcomes")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        status, body = outcome
        return _FakeHttpResponse(status, body)


def _http_error(
    status: int,
    *,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> urllib.error.HTTPError:
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError(
        "https://api.github.test/x", status, "err", message, io.BytesIO(body)
    )


_OK_PERMISSION_BODY = b'{"permission":"admin","user":{"login":"operator"}}'


def _retry_api(monkeypatch: pytest.MonkeyPatch, outcomes: list, **kwargs: object):
    """Build a ``GitHubApi`` wired to a scripted urlopen and a sleep recorder."""
    scripted = _ScriptedUrlopen(outcomes)
    monkeypatch.setattr(urllib.request, "urlopen", scripted)
    sleeps: list[float] = []
    kwargs.setdefault("sleep", sleeps.append)
    kwargs.setdefault("jitter", lambda: 0.5)
    api = AUTHORITY.GitHubApi("https://api.github.test", "token", **kwargs)
    return api, scripted, sleeps


def test_retry_then_succeed_on_transient_503(monkeypatch: pytest.MonkeyPatch) -> None:
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [
            _http_error(503),
            _http_error(503),
            (200, _OK_PERMISSION_BODY),
        ],
    )

    result = api.get_collaborator_permission(REPOSITORY, "operator")

    assert result == {"permission": "admin", "user": {"login": "operator"}}
    assert scripted.calls == 3
    assert len(sleeps) == 2
    for delay in sleeps:
        assert 0 < delay <= AUTHORITY.API_RETRY_MAX_DELAY_SECONDS + AUTHORITY.API_RETRY_BASE_DELAY_SECONDS


def test_retry_exhausted_then_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [_http_error(503) for _ in range(AUTHORITY.API_RETRY_ATTEMPTS)],
    )

    with pytest.raises(AUTHORITY.GitHubApiError) as excinfo:
        api.get_collaborator_permission(REPOSITORY, "operator")

    assert scripted.calls == AUTHORITY.API_RETRY_ATTEMPTS
    assert excinfo.value.kind == "unavailable"
    assert len(sleeps) == AUTHORITY.API_RETRY_ATTEMPTS - 1


@pytest.mark.parametrize("status", [401, 403, 404])
def test_non_retryable_status_fails_immediately_without_retrying(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [_http_error(status, body=b'{"message":"nope"}')],
    )

    with pytest.raises(AUTHORITY.GitHubApiError) as excinfo:
        api.get_collaborator_permission(REPOSITORY, "operator")

    assert scripted.calls == 1
    assert sleeps == []
    assert excinfo.value.kind == "rejected"
    assert excinfo.value.retryable is False


def test_429_with_retry_after_header_is_retried_and_honors_the_server_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [
            _http_error(429, headers={"Retry-After": "2"}),
            (200, _OK_PERMISSION_BODY),
        ],
    )

    result = api.get_collaborator_permission(REPOSITORY, "operator")

    assert result["permission"] == "admin"
    assert scripted.calls == 2
    assert len(sleeps) == 1
    assert sleeps[0] >= 2.0
    assert sleeps[0] <= AUTHORITY.API_RETRY_MAX_DELAY_SECONDS + AUTHORITY.API_RETRY_BASE_DELAY_SECONDS


def test_403_with_ratelimit_remaining_zero_is_rate_limited_not_a_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset = str(int(time.time()) + 30)
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [
            _http_error(
                403,
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset},
            )
            for _ in range(AUTHORITY.API_RETRY_ATTEMPTS)
        ],
    )

    with pytest.raises(AUTHORITY.GitHubApiError) as excinfo:
        api.get_collaborator_permission(REPOSITORY, "operator")

    assert excinfo.value.kind == "rate_limited"
    assert excinfo.value.retryable is True
    assert scripted.calls == AUTHORITY.API_RETRY_ATTEMPTS
    assert len(sleeps) == AUTHORITY.API_RETRY_ATTEMPTS - 1


@pytest.mark.parametrize(
    "make_exc",
    [
        lambda: TimeoutError("timed out"),
        lambda: urllib.error.URLError(TimeoutError("timed out")),
    ],
    ids=["bare_timeout_error", "urlerror_wrapping_timeout"],
)
def test_timeout_is_classified_timeout_and_retried(
    monkeypatch: pytest.MonkeyPatch, make_exc
) -> None:
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [make_exc(), (200, _OK_PERMISSION_BODY)],
    )

    result = api.get_collaborator_permission(REPOSITORY, "operator")

    assert result["permission"] == "admin"
    assert scripted.calls == 2
    assert len(sleeps) == 1


def test_post_is_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    api, scripted, sleeps = _retry_api(monkeypatch, [_http_error(503)])

    with pytest.raises(AUTHORITY.GitHubApiError) as excinfo:
        api.create_check(REPOSITORY, {"name": "ci-authority/main", "head_sha": HEAD})

    assert scripted.calls == 1
    assert sleeps == []
    # A retried POST that had actually succeeded server-side would publish a
    # duplicate check run on the PR head, so this must never retry regardless
    # of the failure's classified retryability.
    assert excinfo.value.kind == "unavailable"


@pytest.mark.parametrize(
    "headers",
    [None, {"Retry-After": "999999"}],
    ids=["no_hint_default_backoff", "far_future_retry_after"],
)
def test_retry_never_sleeps_past_the_total_budget(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str] | None
) -> None:
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [_http_error(503, headers=headers)],
        retry_budget=0.3,
    )

    with pytest.raises(AUTHORITY.GitHubApiError):
        api.get_pull(REPOSITORY, PR_NUMBER)

    assert scripted.calls == 1
    assert sleeps == []
    assert sum(sleeps) <= AUTHORITY.API_RETRY_TOTAL_BUDGET_SECONDS


@pytest.mark.parametrize(
    "kind,expected_reason",
    [
        ("rate_limited", "author_admin_permission_rate_limited"),
        ("timeout", "author_admin_permission_timeout"),
        ("rejected", "author_admin_permission_api_rejected"),
        ("unavailable", "author_admin_permission_api_unavailable"),
    ],
)
def test_reject_reason_names_the_classified_failure_mode_end_to_end(
    kind: str, expected_reason: str
) -> None:
    class KindFailingApi(FakeApi):
        def get_collaborator_permission(self, repository: str, login: str) -> object:
            self.calls.append(("permission", repository, login))
            raise AUTHORITY.GitHubApiError("boom", kind=kind)

    api = KindFailingApi([_file("scripts/run_ci_pack.py")])
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )

    assert code == 1
    assert decision["reason"] == expected_reason
    assert check["status"] == "completed"
    assert check["conclusion"] == "failure"
    assert api.checks[-1] == check


def test_existing_unclassified_exception_still_maps_to_api_unavailable() -> None:
    """A bare exception with no ``kind`` attribute must still fail closed as before."""
    api = FakeApi([_file("scripts/run_ci_pack.py")], fail="permission")
    code, decision, check = AUTHORITY.run_pull_request_target(
        _event(), REPOSITORY, api
    )
    assert code == 1
    assert decision["reason"] == "author_admin_permission_api_unavailable"
    assert check["conclusion"] == "failure"


def test_swallowed_exception_annotation_starts_at_column_zero_on_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        raise ValueError("root cause")
    except ValueError as cause:
        try:
            raise AUTHORITY.GitHubApiError(
                "GitHub GET request failed", kind="timeout", status=None
            ) from cause
        except AUTHORITY.GitHubApiError as raised:
            AUTHORITY._log_api_failure("current_pull", raised)

    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line]
    annotation_lines = [line for line in stdout_lines if line.startswith("::")]

    assert annotation_lines, f"no line starting with '::' in stdout: {captured.out!r}"
    assert len(annotation_lines) == 1
    assert "\n" not in annotation_lines[0]
    assert "current_pull" in annotation_lines[0]


def test_retry_budget_is_consumed_cumulatively_across_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The budget must SHRINK as it is spent, not be re-checked against the total.

    With ``jitter=0.5`` the backoff is deterministic: 0.75s, then 1.5s, then
    3.0s.  A 2.0s budget therefore affords exactly the first sleep (leaving
    1.25s) and must refuse the second (1.5s > 1.25s).  Drop the running
    subtraction and each delay is compared against the full 2.0s instead, so
    a second and third sleep are wrongly allowed — this test is what separates
    a real cumulative budget from a per-delay cap.
    """
    api, scripted, sleeps = _retry_api(
        monkeypatch,
        [_http_error(503) for _ in range(AUTHORITY.API_RETRY_ATTEMPTS)],
        retry_budget=2.0,
    )

    with pytest.raises(AUTHORITY.GitHubApiError) as excinfo:
        api.get_collaborator_permission(REPOSITORY, "operator")

    assert scripted.calls == 2, "budget must stop the loop before the third attempt"
    assert sleeps == [pytest.approx(0.75)]
    assert sum(sleeps) <= 2.0
    # Fail-closed: exhausting the budget rejects, it never returns a verdict.
    assert excinfo.value.retryable is True
    assert excinfo.value.kind == "unavailable"
