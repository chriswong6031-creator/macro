from __future__ import annotations

import importlib.util
import os
import re
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
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for rel in sorted(set(_TEST_PATH_RE.findall(text))):
            if not (ROOT / rel).exists():
                missing.append(f"{workflow.name} -> {rel}")

    assert not missing, (
        "Workflow steps name test files that do not exist:\n  "
        + "\n  ".join(missing)
        + "\n\npytest aborts the ENTIRE invocation on an unresolvable path, so "
        "every other test listed in that step never runs and the job is red for "
        "a reason unrelated to the code. Delete the stale path from the workflow "
        "(or restore the file if the deletion was a mistake)."
    )


# ── self-mod-fence live check: the ship-loop E1 lever must stay satisfiable ───
#
# `gh workflow run ci.yml --ref main` is the documented operator lever (CLAUDE.md,
# ship_loop_guard E1) for clearing every pinned merge with one green main run. On a
# workflow_dispatch there is no `github.base_ref`, so ci-pack renders the fence's
# base as `main` and HEAD *is* main — the three-dot diff is empty by construction.
# Until #3697 that empty list hit R-AUT-5's fail-closed branch and exited 1, so the
# lever could never go green and every dispatch burned a full ~20-min pack (observed
# runs 30207008917 / 30208496248 / 30209369270 / 30210372515, all 2026-07-26).
#
# #3697 shipped the fix as raw shell inside a legacy job that GitHub never runs
# (`if: ${{ false }}`) — only ci-pack executes it, and nothing asserted the behavior.
# These tests render the REAL step out of ci.yml through the REAL pack renderer and
# execute it against a throwaway git repo, so the lever's two halves are pinned:
# dispatch-at-tip passes, and everything else still fails closed.


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=ci@example.com", "-c", "user.name=ci", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


def _fence_live_check_command() -> str:
    """Render the fence's live check exactly as a dispatched ci-pack would.

    workflow_dispatch supplies neither base_ref nor head_ref, so ci-pack's
    `github.base_ref || 'main'` and `github.head_ref || github.ref_name` both
    collapse to the dispatched ref — main.
    """
    job = _yaml(WORKFLOW)["jobs"]["self-mod-fence"]
    steps = [s for s in job["steps"] if "live check" in str(s.get("name", ""))]
    assert len(steps) == 1, f"expected exactly one live-check step, got {len(steps)}"
    return PACK.render_command(str(steps[0]["run"]), base_ref="main", head_ref="main")


def _run_fence(repo: Path, event_name: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GITHUB_EVENT_NAME"] = event_name
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", _fence_live_check_command()],
        cwd=repo, env=env, capture_output=True, text=True,
    )


@pytest.fixture
def dispatch_repo(tmp_path: Path) -> Path:
    """A repo whose HEAD is the tip of `origin/main` — the dispatch-on-main shape."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True, capture_output=True,
    )
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(origin), str(work)], check=True, capture_output=True
    )
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")
    return work


def test_fence_passes_on_dispatch_at_main_tip(dispatch_repo: Path) -> None:
    """The E1 lever must reach green: no PR context means nothing to classify."""
    result = _run_fence(dispatch_repo, "workflow_dispatch")
    assert result.returncode == 0, (
        "`gh workflow run ci.yml --ref main` is the documented ship-loop E1 unblock "
        "lever, and the self-mod-fence live check redded it for an unrelated "
        "structural reason: on a dispatch there is no base_ref, so the fence diffs "
        "main against itself and calls the empty result undeterminable.\n"
        f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_fence_passes_on_dispatch_behind_main_tip(dispatch_repo: Path) -> None:
    """Main advancing between dispatch checkout and this step must not red it."""
    (dispatch_repo / "later.txt").write_text("later\n", encoding="utf-8")
    _git(dispatch_repo, "add", "later.txt")
    _git(dispatch_repo, "commit", "-m", "main moves on")
    _git(dispatch_repo, "push", "origin", "main")
    _git(dispatch_repo, "checkout", "-q", "HEAD~1")  # detach at the dispatched SHA

    result = _run_fence(dispatch_repo, "workflow_dispatch")
    assert result.returncode == 0, (
        "The dispatch arm is written with `merge-base --is-ancestor` rather than "
        "tip-equality precisely so a main that advanced mid-run still passes.\n"
        f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.parametrize("event_name", ["pull_request", "push", ""])
def test_fence_still_fails_closed_without_dispatch(
    dispatch_repo: Path, event_name: str
) -> None:
    """R-AUT-5 is unweakened: an empty diff off a dispatch is still a hard block.

    On a real pull_request an empty changed-file list means the diff genuinely
    failed — shallow clone, base-ref resolution failure, merge-commit HEAD — and
    the fence's own comment is the contract: a fence that errors open is worse
    than no fence. Only the verified dispatch-at-main case may pass.
    """
    result = _run_fence(dispatch_repo, event_name)
    assert result.returncode == 1, (
        f"event_name={event_name!r} produced an empty changed-file list and did NOT "
        "block. The #3697 dispatch arm must stay conditioned on workflow_dispatch; "
        "widening it to all events would silently disarm the self-modification "
        "fence for every PR whose diff cannot be determined.\n"
        f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
