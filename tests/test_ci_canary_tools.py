from __future__ import annotations

import ast
import importlib.util
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SELECT = load("select_ci_canary_packs", ROOT / "scripts" / "select_ci_canary_packs.py")
RESOLVE = load("resolve_ci_canary_ref", ROOT / "scripts" / "resolve_ci_canary_ref.py")
PREWARM = ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_prewarm.py"
ADMISSION = load(
    "runner_admission", ROOT / "ops" / "runner-host" / "common" / "runner_admission.py"
)
CLEANUP = load(
    "runner_cleanup", ROOT / "ops" / "runner-host" / "common" / "runner_cleanup.py"
)
RESOURCE_GUARD = load(
    "mastermind_ci_resource_guard",
    ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_resource_guard.py",
)
COMPARE = load("compare_ci_canary_receipts", ROOT / "scripts" / "compare_ci_canary_receipts.py")
CAPTURE = load("capture_ci_canary_receipt", ROOT / "scripts" / "capture_ci_canary_receipt.py")


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def cache_fixture(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.name", "Canary Test")
    git(source, "config", "user.email", "canary@example.invalid")
    (source / "tracked.txt").write_text("cache-backed\n", encoding="utf-8")
    git(source, "add", "tracked.txt")
    git(source, "commit", "-m", "seed")
    sha = git(source, "rev-parse", "HEAD")
    cache = tmp_path / "cache.git"
    subprocess.run(["git", "clone", "--bare", str(source), str(cache)], check=True, capture_output=True)
    git(cache, "remote", "set-url", "origin", "https://github.com/mastermindx-market-intelligence/macro.git")
    (cache / ".mastermind-cache-identity.json").write_text(
        json.dumps({"schema": "mastermind.ci_git_cache.v1", "repository": "mastermindx-market-intelligence/macro"}) + "\n",
        encoding="utf-8",
    )
    for path in sorted(cache.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode & ~(stat.S_IWGRP | stat.S_IWOTH))
    cache.chmod(cache.stat().st_mode & ~(stat.S_IWGRP | stat.S_IWOTH))
    return cache, sha


def run_prewarm(cache: Path, workspace: Path, sha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(PREWARM),
            "--cache",
            str(cache),
            "--workspace",
            str(workspace),
            "--repository",
            "mastermindx-market-intelligence/macro",
            "--repository-url",
            "https://github.com/mastermindx-market-intelligence/macro.git",
            "--base-sha",
            sha,
            "--expected-owner-uid",
            str(os.getuid()),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_shared_cache_prewarm_materializes_without_origin(tmp_path: Path) -> None:
    cache, sha = cache_fixture(tmp_path)
    workspace = tmp_path / "workspace"
    result = run_prewarm(cache, workspace, sha)
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(workspace, "rev-parse", "HEAD") == sha
    assert (workspace / "tracked.txt").read_text(encoding="utf-8") == "cache-backed\n"
    assert (workspace / ".git" / "objects" / "info" / "alternates").read_text(encoding="utf-8").strip() == str((cache / "objects").resolve())


def test_missing_cache_fails_before_workspace_initialization(tmp_path: Path) -> None:
    result = run_prewarm(tmp_path / "absent.git", tmp_path / "workspace", "0" * 40)
    assert result.returncode == 66
    assert "shared cache unavailable" in result.stdout
    assert not (tmp_path / "workspace" / ".git").exists()


def test_wrong_cache_identity_fails_closed(tmp_path: Path) -> None:
    cache, sha = cache_fixture(tmp_path)
    marker = cache / ".mastermind-cache-identity.json"
    marker.chmod(0o644)
    marker.write_text(
        json.dumps({"schema": "mastermind.ci_git_cache.v1", "repository": "somewhere/else"}),
        encoding="utf-8",
    )
    result = run_prewarm(cache, tmp_path / "workspace", sha)
    assert result.returncode == 66
    assert "identity mismatch" in result.stdout


def test_selector_uses_current_weights_not_a_fixed_pack_number() -> None:
    plan = {
        "schema": SELECT._PLAN_SCHEMA,
        "packs": [
            {"index": 0, "weight": 2, "jobs": ["small"]},
            {"index": 7, "weight": 99, "jobs": ["heavy"]},
            {"index": 4, "weight": 50, "jobs": ["middle"]},
        ],
    }
    assert [item["index"] for item in SELECT.select(plan, 1)] == [7]
    assert [item["index"] for item in SELECT.select(plan, 3)] == [7, 4, 0]


def test_selector_schema_literal_matches_the_live_planner_and_refuses_a_stale_one() -> None:
    """The 2026-08-25 (#6351) defect: a hardcoded 'ci.pack_plan.v1' literal here
    rejected every plan.json the pack runner actually emits (schema
    'ci.pack_plan.v2'), so the canary's own `select` step could never
    succeed. This selector must stay a stdlib-only self-contained script (it
    is copied alone into a trusted-control directory outside the untrusted
    candidate checkout — see the comment in select_ci_canary_packs.py), so it
    cannot import scripts.ci_semantic_proof.PLAN_SCHEMA directly; pin the
    literal against the live constant here instead, and pin that a
    stale/foreign schema is still refused.
    """
    from scripts import ci_semantic_proof as SEMANTIC

    assert SELECT._PLAN_SCHEMA == SEMANTIC.PLAN_SCHEMA == "ci.pack_plan.v2"
    stale_plan = {
        "schema": "ci.pack_plan.v1",
        "packs": [{"index": 0, "weight": 1, "jobs": ["only"]}],
    }
    with pytest.raises(ValueError, match="unexpected CI plan schema"):
        SELECT.select(stale_plan, 1)


def _fragment(**overrides: object) -> dict:
    base = {
        "schema": "ci.semantic_fragment.v1",
        "workflow_run_id": "123",
        "workflow": "infrastructure-selfhosted-ci-canary",
        "event": "workflow_dispatch",
        "role": "pr_head",
        "tested_tree_sha": "a" * 40,
        "subject_head_sha": "b" * 40,
        "base_sha": "c" * 40,
        "plan_sha256": "d" * 64,
        "pack_index": 0,
        "infrastructure": [],
        "jobs": [{"logical_job_id": "demo", "outcome": "passed"}],
    }
    base.update(overrides)
    return base


def _receipt(**overrides: object) -> dict:
    base = {
        "tested_sha": "a" * 40,
        "base_sha": "c" * 40,
        "pack": 0,
        "plan_sha256": "d" * 64,
        "logical_jobs": ["demo"],
        "executed_jobs": ["demo"],
        "failed_jobs": [],
        "result": "passed",
    }
    base.update(overrides)
    return base


def test_compare_never_touches_merge_authority_reconciliation() -> None:
    """Diagnostic-only comparator (#6351 spec C.6): this workflow never calls
    scripts.merge_on_green, and the comparator must never import
    ci_semantic_proof.reconcile_evidence or any other merge-gating entry
    point — only the pure canonicalization helpers.
    """
    assert not hasattr(COMPARE, "reconcile_evidence")
    assert not hasattr(COMPARE, "merge_on_green")
    tree = ast.parse(
        (ROOT / "scripts" / "compare_ci_canary_receipts.py").read_text(encoding="utf-8")
    )
    imported_names = {
        alias.asname or alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "merge_on_green" not in imported_names
    assert "reconcile_evidence" not in imported_names


def test_compare_requires_strict_canonical_fragment_equality() -> None:
    hosted = _receipt()
    selfhosted = _receipt()
    hosted_fragment = _fragment()
    selfhosted_fragment = _fragment()
    assert COMPARE.compare(hosted, selfhosted, hosted_fragment, selfhosted_fragment) == {}

    # Identical identity, different content -> canonical digest catches it.
    diverged = _fragment(jobs=[{"logical_job_id": "demo", "outcome": "failed"}])
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, diverged)
    assert "fragment_canonical_sha256" in mismatches


def test_compare_flags_fragment_identity_mismatch_before_the_digest() -> None:
    hosted = _receipt()
    selfhosted = _receipt()
    hosted_fragment = _fragment()
    wrong_identity = _fragment(tested_tree_sha="f" * 40)
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, wrong_identity)
    assert "fragment_tested_tree_sha" in mismatches
    # Identity validation happens FIRST and short-circuits the byte compare.
    assert "fragment_canonical_sha256" not in mismatches


def test_compare_flags_wrong_fragment_schema() -> None:
    hosted = _receipt()
    selfhosted = _receipt()
    hosted_fragment = _fragment()
    bad_schema = _fragment(schema="ci.semantic_fragment.v0")
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, bad_schema)
    assert "selfhosted_fragment_schema" in mismatches


def test_compare_cross_checks_fragment_identity_against_the_receipt() -> None:
    hosted = _receipt(tested_sha="a" * 40)
    selfhosted = _receipt(tested_sha="a" * 40)
    hosted_fragment = _fragment(tested_tree_sha="e" * 40)
    selfhosted_fragment = _fragment(tested_tree_sha="e" * 40)
    mismatches = COMPARE.compare(hosted, selfhosted, hosted_fragment, selfhosted_fragment)
    assert mismatches == {
        "fragment_receipt_identity": {
            "hosted_fragment_tested_tree_sha": "e" * 40,
            "hosted_receipt_tested_sha": "a" * 40,
        }
    }


def test_capture_receipt_records_fragment_reference_and_bumps_schema(tmp_path: Path) -> None:
    """Materialization-receipt amendment (D, #6351): the receipt now carries
    a v2 schema and a reference to the semantic fragment the same pack
    invocation emitted, so a reader can cross-check receipt identity
    against fragment identity without re-deriving it.
    """
    plan = {"plan_sha256": "d" * 64, "packs": [{"index": 0, "jobs": ["demo"]}]}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    log_path = tmp_path / "pack.log"
    log_path.write_text("::group::demo — proof\nok\nCI_PACK_FAILED_JOBS=[]\n", encoding="utf-8")
    fragment_path = tmp_path / "fragment.json"
    fragment_path.write_text(
        json.dumps({"schema": "ci.semantic_fragment.v1", "plan_sha256": "d" * 64}),
        encoding="utf-8",
    )
    output_path = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
            "--log", str(log_path),
            "--plan", str(plan_path),
            "--pack", "0",
            "--exit-code", "0",
            "--tested-sha", "a" * 40,
            "--base-sha", "b" * 40,
            "--runner-kind", "selfhosted",
            "--runner-name", "test-runner",
            "--fragment", str(fragment_path),
            "--output", str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "ci.selfhosted_canary_receipt.v2"
    assert receipt["fragment_schema"] == "ci.semantic_fragment.v1"
    assert receipt["fragment_plan_sha256"] == "d" * 64
    assert receipt["prewarm_seconds"] is None


def test_capture_receipt_tolerates_a_missing_fragment_reference(tmp_path: Path) -> None:
    plan = {"plan_sha256": "d" * 64, "packs": [{"index": 0, "jobs": ["demo"]}]}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    log_path = tmp_path / "pack.log"
    log_path.write_text("ok\n", encoding="utf-8")
    output_path = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            "python3",
            str(ROOT / "scripts" / "capture_ci_canary_receipt.py"),
            "--log", str(log_path),
            "--plan", str(plan_path),
            "--pack", "0",
            "--exit-code", "0",
            "--tested-sha", "a" * 40,
            "--base-sha", "b" * 40,
            "--runner-kind", "hosted",
            "--runner-name", "test-runner",
            "--output", str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["fragment_schema"] is None
    assert receipt["fragment_plan_sha256"] is None


def test_main_dispatch_freezes_parent_as_the_changed_from_base(monkeypatch) -> None:
    tested = "a" * 40
    parent = "b" * 40

    def fake_git(*args: str) -> str:
        assert args[0] == "rev-parse"
        return tested if args[1].endswith("^{commit}") else parent

    monkeypatch.setattr(RESOLVE, "git", fake_git)
    result = RESOLVE.resolve("mastermindx-market-intelligence/macro", tested, 0, "")
    assert result["tested_ref"] == tested
    assert result["tested_sha"] == tested
    assert result["base_sha"] == parent
    assert result["contamination_sha"] == parent


def test_pr_dispatch_uses_the_fetched_merge_parent_when_api_base_is_stale(
    monkeypatch,
) -> None:
    """The merge ref is the tested tree; its first parent is its tested base.

    GitHub's pull-request ``base.sha`` can lag the first parent of the current
    synthetic merge ref while the PR head and immutable merge SHA remain exact.
    """
    merge = "a" * 40
    tested_base = "b" * 40
    head = "c" * 40
    stale_api_base = "d" * 40
    monkeypatch.setattr(
        RESOLVE,
        "pull_request",
        lambda *_: {
            "state": "open",
            "merge_commit_sha": merge,
            "base": {"ref": "main", "sha": stale_api_base},
            "head": {
                "sha": head,
                "repo": {"full_name": "mastermindx-market-intelligence/macro"},
            },
        },
    )

    def fake_git(*args: str) -> str:
        if args[0] == "fetch":
            return ""
        revisions = {
            "refs/ci-canary/pull/7/merge^{commit}": merge,
            f"{merge}^1": tested_base,
            f"{merge}^2": head,
        }
        return revisions[args[1]]

    monkeypatch.setattr(RESOLVE, "git", fake_git)
    result = RESOLVE.resolve(
        "mastermindx-market-intelligence/macro", "e" * 40, 7, "token"
    )
    assert result["tested_sha"] == merge
    assert result["base_sha"] == tested_base
    assert result["head_sha"] == head
    assert result["contamination_sha"] == tested_base


def test_pr_dispatch_requires_fetched_merge_sha_and_head_to_match_api(monkeypatch) -> None:
    merge = "a" * 40
    base = "b" * 40
    head = "c" * 40
    monkeypatch.setattr(
        RESOLVE,
        "pull_request",
        lambda *_: {
            "state": "open",
            "merge_commit_sha": merge,
            "base": {"ref": "main", "sha": base},
            "head": {
                "sha": head,
                "repo": {"full_name": "mastermindx-market-intelligence/macro"},
            },
        },
    )

    def fake_git(*args: str) -> str:
        if args[0] == "fetch":
            return ""
        revisions = {
            "refs/ci-canary/pull/7/merge^{commit}": merge,
            f"{merge}^1": base,
            f"{merge}^2": head,
        }
        return revisions[args[1]]

    monkeypatch.setattr(RESOLVE, "git", fake_git)
    result = RESOLVE.resolve(
        "mastermindx-market-intelligence/macro", "d" * 40, 7, "token"
    )
    assert result["tested_sha"] == merge
    assert result["base_sha"] == base
    assert result["head_sha"] == head

    monkeypatch.setattr(RESOLVE, "git", lambda *args: "e" * 40 if args[0] != "fetch" else "")
    try:
        RESOLVE.resolve("mastermindx-market-intelligence/macro", "d" * 40, 7, "token")
    except RESOLVE.ResolutionError as exc:
        assert "merge" in str(exc)
    else:
        raise AssertionError("mismatched merge/API parents must fail closed")


def test_host_admission_accepts_only_the_main_dispatch_canary() -> None:
    allowed = {
        "MASTERMIND_CI_PROFILE": "pc-ci",
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "selfhosted-ci-canary.yml@refs/heads/main"
        ),
        "GITHUB_JOB": "selfhosted-pack",
    }
    assert ADMISSION.decision(allowed)[0]
    for key, value in (
        ("GITHUB_EVENT_NAME", "pull_request"),
        ("GITHUB_REF", "refs/pull/7/merge"),
        ("GITHUB_WORKFLOW_REF", "mastermindx-market-intelligence/macro/.github/workflows/rogue.yml@refs/heads/main"),
        ("GITHUB_REPOSITORY", "attacker/fork"),
    ):
        mutated = {**allowed, key: value}
        assert not ADMISSION.decision(mutated)[0]


def test_host_admission_accepts_only_the_main_dispatch_trusted_executor_pack() -> None:
    allowed = {
        "MASTERMIND_CI_PROFILE": "pc-ci",
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "trusted-ci-executor.yml@refs/heads/main"
        ),
        "GITHUB_JOB": "trusted-pack",
    }
    assert ADMISSION.decision(allowed)[0]
    for key, value in (
        ("GITHUB_EVENT_NAME", "workflow_call"),
        ("GITHUB_REF", "refs/pull/7/merge"),
        (
            "GITHUB_WORKFLOW_REF",
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "trusted-ci-executor.yml@refs/heads/candidate",
        ),
        (
            "GITHUB_WORKFLOW_REF",
            "mastermindx-market-intelligence/macro/.github/workflows/"
            "hostile-main-caller.yml@refs/heads/main",
        ),
        ("GITHUB_REPOSITORY", "attacker/fork"),
        ("GITHUB_JOB", "rogue-pack"),
    ):
        mutated = {**allowed, key: value}
        assert not ADMISSION.decision(mutated)[0]


def test_host_admission_accepts_only_main_gated_same_repo_pr_executor_pack() -> None:
    pr_number = "6505"
    allowed = {
        "MASTERMIND_CI_PROFILE": "pc-ci",
        "GITHUB_REPOSITORY": "mastermindx-market-intelligence/macro",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": f"refs/pull/{pr_number}/merge",
        "GITHUB_WORKFLOW_REF": (
            "mastermindx-market-intelligence/macro/.github/workflows/"
            f"ci.yml@refs/pull/{pr_number}/merge"
        ),
        "GITHUB_JOB": "trusted-pack",
        "MASTERMIND_TRUSTED_HEAD_REPOSITORY": (
            "mastermindx-market-intelligence/macro"
        ),
        "MASTERMIND_TRUSTED_BASE_REF": "main",
        "MASTERMIND_TRUSTED_CONTROL_SHA": "a" * 40,
    }
    assert ADMISSION.decision(allowed)[0]
    for key, value in (
        ("GITHUB_EVENT_NAME", "workflow_dispatch"),
        ("GITHUB_REF", "refs/pull/6506/merge"),
        (
            "GITHUB_WORKFLOW_REF",
            "mastermindx-market-intelligence/macro/.github/workflows/rogue.yml@refs/pull/6505/merge",
        ),
        ("GITHUB_JOB", "rogue-pack"),
        ("MASTERMIND_TRUSTED_HEAD_REPOSITORY", "attacker/fork"),
        ("MASTERMIND_TRUSTED_BASE_REF", "release"),
        ("MASTERMIND_TRUSTED_CONTROL_SHA", "candidate"),
    ):
        assert not ADMISSION.decision({**allowed, key: value})[0]


def test_cache_update_disables_automatic_maintenance() -> None:
    script = (ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_cache_update.sh").read_text(
        encoding="utf-8"
    )
    assert "fetch --no-auto-maintenance" in script
    assert "config gc.auto 0" in script
    assert "config maintenance.auto false" in script


def test_runner_service_seals_runtime_and_binds_host_admission() -> None:
    unit = (
        ROOT / "ops" / "runner-host" / "pc" / "actions-runner-ci.service.template"
    ).read_text(encoding="utf-8")
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/libexec/mastermind-ci-admission-pc-ci.js" in unit
    assert "ACTIONS_RUNNER_HOOK_JOB_COMPLETED" not in unit
    assert "Restart=always" in unit
    assert "RestartSec=5" in unit
    assert "StartLimitIntervalSec=0" in unit
    assert "StartLimitBurst" not in unit
    assert "--refusal-backoff-seconds 300" in unit
    assert "TimeoutStartSec=10min" in unit
    assert "MASTERMIND_CI_RUNNER_ROOT=__RUNNER_ROOT__" in unit
    assert "ReadOnlyPaths=__RUNNER_ROOT__ /var/cache/mastermind-ci/macro.git" in unit
    assert "ReadWritePaths=__RUNNER_ROOT__/_work __RUNNER_ROOT__/_diag" in unit
    assert "ReadWritePaths=__RUNNER_ROOT__ " not in unit
    assert "UMask=0022" in unit
    assert "UMask=0027" not in unit
    pc_wrapper = (
        ROOT / "ops" / "runner-host" / "pc" / "mastermind_ci_runner.sh"
    ).read_text(encoding="utf-8")
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/libexec/mastermind-ci-admission-pc-ci.js" in pc_wrapper
    assert "/usr/bin/python3 -I /usr/local/libexec/runner_cleanup.py" in pc_wrapper
    assert 'run --startuptype service --once' in pc_wrapper
    assert 'MASTERMIND_CI_RUNNER_ROOT="$runner_root"' in pc_wrapper
    m1 = (ROOT / "ops" / "runner-host" / "m1" / "run_guarded_runner.sh").read_text(
        encoding="utf-8"
    )
    assert 'ACTIONS_RUNNER_HOOK_JOB_STARTED="$guard_root/runner_admission_m1_canary.js"' in m1
    assert "MASTERMIND_CI_PROFILE=m1-canary" in m1
    hook = (
        ROOT / "ops" / "runner-host" / "common" / "runner_admission_hook.js"
    ).read_text(encoding="utf-8")
    assert 'spawnSync("/usr/bin/python3", ["-I", script]' in hook
    assert "process.env.PATH" not in hook
    assert "process.env.MASTERMIND_CI_PROFILE" not in hook


def test_resource_refusal_backoff_only_delays_an_unsafe_retry() -> None:
    sleeps: list[int] = []
    RESOURCE_GUARD.refusal_backoff([], 300, sleep=sleeps.append)
    assert sleeps == []
    RESOURCE_GUARD.refusal_backoff(["critical disk pressure"], 300, sleep=sleeps.append)
    assert sleeps == [300]


def test_listener_startup_cleanup_scrubs_all_pc_job_state_and_recreates_runtime_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    runner = tmp_path / "runner-1"
    work = runner / "_work"
    (work / "_temp").mkdir(parents=True)
    (work / "_temp" / "current-event.json").write_text("{}", encoding="utf-8")
    (work / "macro" / "macro").mkdir(parents=True)
    (work / "macro" / "macro" / "sentinel").write_text("old", encoding="utf-8")
    (work / "_actions").mkdir()
    (work / "_tool").symlink_to(work / "macro", target_is_directory=True)
    private_tmp = tmp_path / "private-tmp"
    private_tmp.mkdir()
    (private_tmp / "prior-job").write_text("old", encoding="utf-8")
    monkeypatch.setattr(CLEANUP, "PC_CI_ROOTS", {runner})
    assert CLEANUP.scrub_pc_state(runner, (private_tmp,)) >= 4
    assert not (work / "_temp" / "current-event.json").exists()
    assert list((work / "_temp").iterdir()) == []
    assert list((work / "_home").iterdir()) == []
    assert not (work / "macro").exists()
    assert not (work / "_actions").exists()
    assert not (work / "_tool").exists()
    assert list(private_tmp.iterdir()) == []


def test_start_admission_has_no_workspace_mutation_api() -> None:
    assert not hasattr(ADMISSION, "scrub_pc_state")
    assert not hasattr(ADMISSION, "remove_entry")
