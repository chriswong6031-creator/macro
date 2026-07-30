from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
MANIFEST = ROOT / ".github" / "ci" / "legacy-jobs.yml"
FENCES = ROOT / ".github" / "workflows" / "fences.yml"

SPEC = importlib.util.spec_from_file_location(
    "run_ci_pack", ROOT / "scripts" / "run_ci_pack.py"
)
assert SPEC and SPEC.loader
PACK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACK
SPEC.loader.exec_module(PACK)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_all_legacy_jobs_are_disabled_and_packable() -> None:
    jobs = PACK.load_legacy_jobs(MANIFEST)
    assert len(jobs) >= 86
    assert all(job.definition["if"] == PACK.DISABLED_IF for job in jobs)


def test_two_packs_are_complete_disjoint_and_balanced() -> None:
    jobs = PACK.load_legacy_jobs(MANIFEST)
    packs = PACK.partition_jobs(jobs, 2)
    flattened = [job.job_id for pack in packs for job in pack]
    assert sorted(flattened) == sorted(job.job_id for job in jobs)
    assert len(flattened) == len(set(flattened))

    weights = [sum(job.weight for job in pack) for pack in packs]
    assert max(weights) - min(weights) <= max(job.weight for job in jobs)


def test_legacy_expressions_are_supported() -> None:
    for job in PACK.load_legacy_jobs(MANIFEST):
        for step in job.definition["steps"]:
            if "run" not in step:
                continue
            rendered = PACK.render_command(
                str(step["run"]), base_ref="main", head_ref="claude/example"
            )
            assert "${{" not in rendered


def test_unknown_job_semantics_fail_closed(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  unsafe:
    if: ${{ false }}
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres
    steps:
      - run: echo unsafe
"""
    )
    with pytest.raises(PACK.ManifestError, match="unsupported keys: services"):
        PACK.load_legacy_jobs(workflow)


def test_execute_refuses_to_clean_a_developer_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    with pytest.raises(RuntimeError, match="only inside GitHub Actions"):
        PACK._workspace_root()


def test_execution_restores_workspace_between_legacy_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "checkout"
    repo.mkdir()
    workflow = repo / "ci.yml"
    workflow.write_text(
        """
jobs:
  ci-pack:
    runs-on: ubuntu-latest
    steps:
      - run: echo pack
  first:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - run: printf leak > leaked.tmp
  second:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - run: test ! -e leaked.tmp
"""
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "ci-pack@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI Pack Test"], cwd=repo, check=True
    )
    subprocess.run(["git", "add", "ci.yml"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True
    )

    monkeypatch.chdir(repo)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(repo))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    jobs = PACK.load_legacy_jobs(workflow)
    assert PACK.execute_pack(jobs) == 0
    assert not (repo / "leaked.tmp").exists()


def test_workflows_cancel_superseded_pr_runs() -> None:
    ci = _yaml(WORKFLOW)
    fences = _yaml(FENCES)
    for workflow in (ci, fences):
        assert workflow["concurrency"]["cancel-in-progress"] is True
    assert "pull_request.number" in ci["concurrency"]["group"]
    assert "github.ref" in ci["concurrency"]["group"]
    assert "pull_request.number" in fences["concurrency"]["group"]


def test_ci_pack_is_a_few_hosted_jobs_not_eighty_six() -> None:
    workflow = _yaml(WORKFLOW)
    assert set(workflow["jobs"]) == {"ci-pack"}
    pack = workflow["jobs"]["ci-pack"]
    # The pack COUNT tunes (2 -> 4 on 2026-07-28 to halve time-to-green); the
    # SHAPE is the contract: a small ordered matrix of balanced packs on hosted
    # runners, never one job per legacy suite (86 VMs), and the matrix must
    # agree with the --pack-count handed to the runner or some packs' jobs
    # would execute nowhere.
    matrix = pack["strategy"]["matrix"]["pack"]
    assert matrix == list(range(len(matrix)))
    assert 2 <= len(matrix) <= 8
    assert pack["runs-on"] == "ubuntu-latest"
    assert pack["strategy"]["fail-fast"] is False
    assert pack["if"] == "github.event.action != 'closed'"
    run_text = "\n".join(
        str(step.get("run", "")) for step in pack["steps"] if isinstance(step, dict)
    )
    assert "--workflow .github/ci/legacy-jobs.yml" in run_text
    assert f"--pack-count {len(matrix)}" in run_text

    # A manifest edit must trigger CI even though GitHub does not interpret the
    # manifest itself as a workflow.
    triggers = workflow.get("on") or workflow.get(True)
    assert ".github/ci/legacy-jobs.yml" in triggers["pull_request"]["paths"]
    assert "closed" in triggers["pull_request"]["types"]


def test_ci_pack_partial_clone_keeps_history_without_historical_site_blobs() -> None:
    """Full history is load-bearing; full historical blob transfer is not.

    The four #4053 hosted runners spent 6m45s-14m39s in checkout before tests.
    ``filter: blob:none`` preserves the complete current working tree and commit
    graph while omitting historical generated-site blobs from the initial fetch.
    Do not replace this with sparse checkout: legacy suites legitimately inspect
    current ``site/`` files.
    """
    workflow = _yaml(WORKFLOW)
    pack = workflow["jobs"]["ci-pack"]
    checkout = next(
        step
        for step in pack["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["filter"] == "blob:none"
    assert checkout["with"]["fetch-depth"] == 0
    assert "sparse-checkout" not in checkout["with"]


def test_same_repo_fences_share_one_runner_and_keep_required_contexts() -> None:
    workflow = _yaml(FENCES)
    assert workflow["permissions"]["checks"] == "write"
    jobs = workflow["jobs"]
    pack = jobs["fence-pack"]
    assert pack["runs-on"] == "ubuntu-latest"

    publish = next(step for step in pack["steps"] if step.get("id") == "publish")
    assert publish["if"] == "always()"
    assert publish["uses"].startswith("actions/github-script@")
    script = publish["with"]["script"]
    for context in ("self-mod-fence", "capability-broker", "grader-manifest"):
        assert f"name: '{context}'" in script
    assert "github.rest.checks.create" in script

    # Fork tokens cannot write check runs. Their compatibility jobs retain the
    # exact contexts only when the PR truly comes from a fork; on the high-volume
    # same-repo path their skipped names are deliberately different, so they
    # cannot satisfy a required fence before fence-pack publishes its verdict.
    for job_id, context in (
        ("fork-self-mod-fence", "self-mod-fence"),
        ("fork-capability-broker", "capability-broker"),
        ("fork-grader-manifest", "grader-manifest"),
    ):
        fallback = jobs[job_id]
        assert "head.repo.full_name != github.repository" in fallback["if"]
        assert context in fallback["name"]
        assert f"fork-{context}-unused" in fallback["name"]


# ── every tests/*.py a workflow names must exist ─────────────────────────────
#
# `pytest a.py b.py missing.py` does not skip the missing path — it aborts the
# whole invocation with "ERROR: file or directory not found" and runs NOTHING.
# So one deleted test file silently disables every other test in its step.
# ci-main-heartbeat's engine-render-guards step listed
# tests/test_leadership_board.py, deleted with the Mag-7 board in #3359; the job
# had been erroring out ever since, taking 2084 passing tests in the other 73
# files down with it, and main's heartbeat red, until #3555.
#
# This is the [[ci-trigger-must-reach-the-guard]] class one turn worse: there the
# guard could not be triggered, here it is triggered and then never runs. A red
# job is not evidence that the tests under it ran.

_TEST_PATH_RE = re.compile(r'(?<![\w/-])(tests/[A-Za-z0-9_][A-Za-z0-9_./-]*\.py)')


def test_every_workflow_test_path_exists() -> None:
    """No workflow may name a tests/*.py file that is not on disk."""
    missing: list[str] = []
    checked = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + [MANIFEST]
    for workflow_or_manifest in checked:
        text = workflow_or_manifest.read_text(encoding="utf-8")
        for rel in sorted(set(_TEST_PATH_RE.findall(text))):
            if not (ROOT / rel).exists():
                missing.append(f"{workflow_or_manifest.name} -> {rel}")

    assert not missing, (
        "Workflow steps name test files that do not exist:\n  "
        + "\n  ".join(missing)
        + "\n\npytest aborts the ENTIRE invocation on an unresolvable path, so "
        "every other test listed in that step never runs and the job is red for "
        "a reason unrelated to the code. Delete the stale path from the workflow "
        "(or restore the file if the deletion was a mistake)."
    )
