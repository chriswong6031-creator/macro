from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
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
    jobs = PACK.load_legacy_jobs(WORKFLOW)
    assert len(jobs) >= 86
    assert all(job.definition["if"] == PACK.DISABLED_IF for job in jobs)


def test_two_packs_are_complete_disjoint_and_balanced() -> None:
    jobs = PACK.load_legacy_jobs(WORKFLOW)
    packs = PACK.partition_jobs(jobs, 2)
    flattened = [job.job_id for pack in packs for job in pack]
    assert sorted(flattened) == sorted(job.job_id for job in jobs)
    assert len(flattened) == len(set(flattened))

    weights = [sum(job.weight for job in pack) for pack in packs]
    assert max(weights) - min(weights) <= max(job.weight for job in jobs)


def test_legacy_expressions_are_supported() -> None:
    for job in PACK.load_legacy_jobs(WORKFLOW):
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
    assert "pull_request.number" in fences["concurrency"]["group"]


def test_ci_pack_is_two_hosted_jobs_not_eighty_six() -> None:
    workflow = _yaml(WORKFLOW)
    pack = workflow["jobs"]["ci-pack"]
    assert pack["strategy"]["matrix"]["pack"] == [0, 1]
    assert pack["runs-on"] == "ubuntu-latest"
    assert pack["strategy"]["fail-fast"] is False
