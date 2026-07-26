"""tests/test_self_mod_fence.py — F2 self-modification fence tests.

Four test groups (matching the spec):
  1. Loop PR touching immutable path → BLOCKED
  2. Human PR touching same immutable path → allowed
  3. Loop PR touching non-immutable path → allowed
  4. Unclassifiable input → BLOCKED (fail-closed)

Plus selftest, and group 7: the packed CI manifest's *live check* shell itself,
which the Python `check()` above never exercised.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.check_self_mod_fence import check, selftest, IMMUTABLE_PATTERNS, LOOP_BRANCH_PREFIXES
from scripts.run_ci_pack import render_command


# ── 1. Loop PR + immutable path → BLOCKED ────────────────────────────────────

@pytest.mark.parametrize("branch,files,trailers,label", [
    (
        "metabolism/propose-til",
        ["config/grader_manifest.yml"],
        "",
        "loop branch prefix + grader_manifest",
    ),
    (
        "claude/loop-build-something",
        [".github/workflows/ci.yml"],
        "",
        "claude/loop- prefix + workflow file",
    ),
    (
        "claude/loop-build-something",
        [".github/ci/legacy-jobs.yml"],
        "",
        "claude/loop- prefix + packed CI manifest",
    ),
    (
        "metabolism/owns-broker",
        ["engine/neuralweb/capability_broker.py"],
        "",
        "loop branch + capability_broker.py",
    ),
    (
        "metabolism/owns-hooks",
        [".claude/hooks/model_routing_guard.py"],
        "",
        "loop branch + .claude/hooks/**",
    ),
    (
        "metabolism/adj",
        ["scripts/check_self_mod_fence.py"],
        "",
        "loop branch + check_self_mod_fence.py itself",
    ),
    (
        "metabolism/adj",
        ["scripts/check_grader_manifest.py"],
        "",
        "loop branch + check_grader_manifest.py",
    ),
    (
        "metabolism/adj",
        ["config/capability_manifest.yml"],
        "",
        "loop branch + capability_manifest.yml",
    ),
    (
        "metabolism/adj",
        ["config/metabolism_budget.yml"],
        "",
        "loop branch + metabolism_budget.yml",
    ),
    (
        "metabolism/adj",
        ["research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md"],
        "",
        "loop branch + masterplan (tier table)",
    ),
    # SA-R2/SA-R4: standout ruler files must be blocked
    (
        "metabolism/neuter-guards",
        [".claude/settings.json"],
        "",
        "loop branch + .claude/settings.json (hook-wiring guard)",
    ),
    (
        "metabolism/neuter-guards",
        [".claude/settings.local.json"],
        "",
        "loop branch + .claude/settings.local.json (hook-wiring guard)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["engine/standout_audit.py"],
        "",
        "loop branch + engine/standout_audit.py (SA-R2 US taxonomy ruler)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["engine/china_standout_audit.py"],
        "",
        "loop branch + engine/china_standout_audit.py (SA-R2 CN taxonomy ruler)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["engine/standout_review.py"],
        "",
        "loop branch + engine/standout_review.py (SA-R4 clamp enforcement)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["config/standout_review.yml"],
        "",
        "loop branch + config/standout_review.yml (SA-R4 clamp values)",
    ),
    (
        "claude/human-pr-with-trailer",
        ["config/grader_manifest.yml"],
        "Loop-Authored: propose-lobe run=abc123",
        "loop trailer + immutable path (even on human-looking branch)",
    ),
])
def test_loop_pr_immutable_is_blocked(branch, files, trailers, label):
    """Loop PRs touching the IMMUTABLE set must be BLOCKED."""
    rc, msg = check(branch=branch, changed_files=files, trailers_text=trailers)
    assert rc != 0, (
        f"[{label}] Expected BLOCKED but got PASS. "
        f"Branch='{branch}', files={files}. Message: {msg[:200]}"
    )
    assert "BLOCKED" in msg, f"[{label}] Message should say BLOCKED: {msg[:200]}"


# ── 2. Human PR + immutable path → allowed ───────────────────────────────────

@pytest.mark.parametrize("branch,files,label", [
    (
        "claude/eloquent-kilby-64ffe7",
        ["config/grader_manifest.yml"],
        "human worktree branch + grader_manifest",
    ),
    (
        "feature/update-ci",
        [".github/workflows/ci.yml"],
        "feature branch + workflow file",
    ),
    (
        "main",
        ["scripts/check_grader_manifest.py"],
        "main branch + check script",
    ),
    (
        "fix/capability-broker-patch",
        ["engine/neuralweb/capability_broker.py"],
        "human fix branch + broker",
    ),
    (
        "claude/metabolism-phase0-cage",
        ["config/grader_manifest.yml", ".github/workflows/ci.yml"],
        "this PR's own branch (human worktree) + immutable files",
    ),
])
def test_human_pr_immutable_is_allowed(branch, files, label):
    """Human PRs (no loop namespace or trailer) pass freely, even touching immutable paths."""
    rc, msg = check(branch=branch, changed_files=files, trailers_text="")
    assert rc == 0, (
        f"[{label}] Expected PASS but got BLOCKED. "
        f"Branch='{branch}'. Message: {msg[:200]}"
    )


# ── 3. Loop PR + non-immutable path → allowed ────────────────────────────────

@pytest.mark.parametrize("branch,files,label", [
    (
        "metabolism/til-fitness-card",
        ["engine/neuralweb/til_fitness.py", "data/metabolism/fitness/til.json"],
        "loop branch + new organ files",
    ),
    (
        "claude/loop-propose-til",
        ["data/metabolism/journal/cycle_001.json"],
        "loop propose branch + journal artifact",
    ),
    (
        "metabolism/learn-cycle",
        ["docs/AUTONOMY_LOG.md", "data/neuralweb/governance.jsonl"],
        "loop learn branch + docs and governance log",
    ),
])
def test_loop_pr_non_immutable_is_allowed(branch, files, label):
    """Loop PRs touching only non-immutable paths pass freely."""
    rc, msg = check(branch=branch, changed_files=files, trailers_text="")
    assert rc == 0, (
        f"[{label}] Expected PASS but got BLOCKED. "
        f"Branch='{branch}'. Message: {msg[:200]}"
    )


# ── 4. Unclassifiable → BLOCKED (fail-closed) ────────────────────────────────

def test_empty_branch_is_fail_closed():
    """Empty branch name → unclassifiable → BLOCKED."""
    rc, msg = check(branch="", changed_files=["anything.py"])
    assert rc != 0, "Empty branch must be BLOCKED (fail-closed)"
    assert "BLOCKED" in msg


# ── 5. Selftest ───────────────────────────────────────────────────────────────

def test_selftest_passes():
    """The built-in selftest covers all required cases."""
    rc = selftest()
    assert rc == 0, "check_self_mod_fence selftest must pass"


# ── 6. Pattern coverage ───────────────────────────────────────────────────────

def test_immutable_patterns_cover_all_required_paths():
    """Every path required by the spec appears in IMMUTABLE_PATTERNS."""
    required = [
        ".claude/hooks/",
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".github/workflows/",
        "config/grader_manifest.yml",
        "config/capability_manifest.yml",
        "config/metabolism_budget.yml",
        "engine/neuralweb/capability_broker.py",
        "scripts/check_self_mod_fence.py",
        "scripts/check_grader_manifest.py",
        "research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md",
        # SA-R2/SA-R4 standout ruler files
        "engine/standout_audit.py",
        "engine/china_standout_audit.py",
        "engine/standout_review.py",
        "config/standout_review.yml",
    ]
    for req in required:
        # At least one pattern must match the required path or be a prefix
        found = any(
            req in p or p.replace("/**", "").replace("**", "") in req
            for p in IMMUTABLE_PATTERNS
        )
        assert found, (
            f"Required immutable path '{req}' not covered by any IMMUTABLE_PATTERNS entry."
        )


def test_loop_branch_prefixes_are_defined():
    """The loop branch prefixes list is non-empty."""
    assert LOOP_BRANCH_PREFIXES, "LOOP_BRANCH_PREFIXES must be non-empty"
    assert "metabolism/" in LOOP_BRANCH_PREFIXES
    assert any("loop-" in p for p in LOOP_BRANCH_PREFIXES)


# ── 7. The packed CI live-check SHELL (not just the Python fence) ─────────────
#
# Everything above tests check_self_mod_fence.check().  The step that actually
# runs in CI is a bash block in .github/ci/legacy-jobs.yml, and that block owns
# a decision `check()` never sees: what to do when the changed-file list comes
# back EMPTY.  R-AUT-5 says an undeterminable diff must BLOCK — but on
# `workflow_dispatch --ref main` (the ship-loop guard's E1 unblock lever,
# CLAUDE.md) HEAD *is* origin/main, so `git diff origin/main...HEAD` is empty by
# construction and the fail-closed arm redded every dispatch run.  That made the
# only documented way to clear a base-side red pinned onto an already-merged PR
# unsatisfiable (observed runs 30207008917 / 30209369270 / 30210445220,
# 2026-07-26); #3697 added the dispatch arm but shipped it with no test.
#
# These tests execute the REAL step text from the manifest, rendered through the REAL
# production renderer (run_ci_pack.render_command — the packs are what actually
# run, every legacy job carries `if: ${{ false }}`), against synthetic git
# repositories.  Both directions are pinned: the lever must pass, and every other
# empty-diff shape must still block.

LIVE_CHECK_STEP = "self-mod-fence live check (loop PR + immutable → BLOCKED)"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _fence_step_run(workflow_relpath: str, step_name: str) -> dict:
    """Return the named self-mod-fence step, failing loudly if it moved.

    A renamed or deleted step must break these tests rather than silently
    reducing them to a no-op — the guard has to fail when its subject vanishes.
    """
    payload = yaml.safe_load((REPO_ROOT / workflow_relpath).read_text())
    job_id = "fence-pack" if workflow_relpath.endswith("/fences.yml") else "self-mod-fence"
    steps = payload["jobs"][job_id]["steps"]
    for step in steps:
        if str(step.get("name", "")) == step_name:
            return step
    raise AssertionError(
        f"{workflow_relpath}: {job_id} has no step named {step_name!r} "
        f"(found: {[s.get('name') for s in steps]}). Update this test with the "
        "step so the live check keeps its coverage."
    )


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _seed_repo(tmp_path: Path) -> Path:
    """A throwaway origin + clone: one commit on main, fence script in place."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True, capture_output=True,
    )
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(origin), str(work)], check=True, capture_output=True
    )
    hooks = tmp_path / "nohooks"
    hooks.mkdir()
    for key, value in (
        ("user.email", "fence-test@example.invalid"),
        ("user.name", "fence test"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(hooks)),
    ):
        _git("config", key, value, cwd=work)

    (work / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO_ROOT / "scripts/check_self_mod_fence.py",
        work / "scripts/check_self_mod_fence.py",
    )
    (work / "README.md").write_text("base\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "base", cwd=work)
    _git("push", "origin", "main", cwd=work)
    return work


def _run_live_check(
    work: Path, *, event: str, head_ref: str, base_ref: str = "main"
) -> subprocess.CompletedProcess:
    """Render the manifest step exactly as ci-pack does, then run it."""
    command = render_command(
        str(_fence_step_run(".github/ci/legacy-jobs.yml", LIVE_CHECK_STEP)["run"]),
        base_ref=base_ref,
        head_ref=head_ref,
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GITHUB_EVENT_NAME"] = event
    # ci-pack runs every legacy step through this exact interpreter invocation.
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", command],
        cwd=work, env=env, capture_output=True, text=True,
    )


def test_live_check_passes_workflow_dispatch_on_main(tmp_path):
    """`gh workflow run ci.yml --ref main` must PASS, not fail closed.

    This is the E1 unblock lever CLAUDE.md documents. HEAD is origin/main, so the
    three-dot diff is empty by construction; before #3697 that hit the
    fail-closed arm and the lever could never produce a green run.
    """
    work = _seed_repo(tmp_path)
    result = _run_live_check(work, event="workflow_dispatch", head_ref="")
    assert result.returncode == 0, (
        "dispatch-on-main must pass the live check — the E1 lever is "
        f"unsatisfiable otherwise.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "zero changes to classify" in result.stdout


def test_live_check_passes_dispatch_when_main_advanced_past_head(tmp_path):
    """The arm tests ancestry, not tip equality, so a moving main stays green.

    main can advance between the dispatch checkout and this step (it is a busy
    shared branch); HEAD is then a strict ancestor and the diff is still
    verified-empty.
    """
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "advance", cwd=work)
    (work / "later.txt").write_text("later\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "main advances after checkout", cwd=work)
    _git("push", "origin", "advance:main", cwd=work)
    _git("checkout", "main", cwd=work)  # HEAD = the older commit

    result = _run_live_check(work, event="workflow_dispatch", head_ref="")
    assert result.returncode == 0, (
        "HEAD strictly behind origin/main is still verified-empty.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "zero changes to classify" in result.stdout


def test_live_check_blocks_pull_request_with_empty_diff(tmp_path):
    """R-AUT-5 fail-closed stays intact: a PR whose diff is empty is BLOCKED.

    The dispatch arm must not widen into "any empty diff passes" — a fence that
    errors open is worse than no fence.
    """
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "claude/loop-no-commits", cwd=work)

    result = _run_live_check(
        work, event="pull_request", head_ref="claude/loop-no-commits"
    )
    assert result.returncode == 1, (
        "an empty-diff PR must still fail closed.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "fail-closed" in result.stderr


def test_live_check_blocks_dispatch_whose_head_is_not_on_main(tmp_path):
    """The ancestry probe is load-bearing — the event name alone must not pass.

    A dispatched ref that is NOT on main can still produce an empty three-dot
    diff (a sibling commit whose tree matches the merge base). That diff is not
    verified-empty, so it must block.
    """
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "sibling", cwd=work)
    _git("commit", "--allow-empty", "-m", "sibling commit, no tree change", cwd=work)
    _git("checkout", "main", cwd=work)
    _git("commit", "--allow-empty", "-m", "main diverges", cwd=work)
    _git("push", "origin", "main", cwd=work)
    _git("checkout", "sibling", cwd=work)

    result = _run_live_check(work, event="workflow_dispatch", head_ref="")
    assert result.returncode == 1, (
        "a dispatched HEAD that is not an ancestor of main is not "
        f"verified-empty.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "fail-closed" in result.stderr


def test_live_check_still_blocks_loop_pr_touching_immutable(tmp_path):
    """End-to-end: the shell still reaches the Python fence and blocks."""
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "metabolism/self-edit", cwd=work)
    (work / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (work / ".github/workflows/ci.yml").write_text("jobs: {}\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "loop edits an immutable path", cwd=work)

    result = _run_live_check(
        work, event="pull_request", head_ref="metabolism/self-edit"
    )
    assert result.returncode != 0, (
        "loop branch + immutable path must stay BLOCKED.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "BLOCKED" in result.stderr, (
        f"fence failed without its fail-closed diagnostic (rc={result.returncode}).\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_fences_workflow_live_check_is_pull_request_only():
    """The fences.yml twin has no dispatch arm — its `if:` is what keeps it sound.

    fences.yml carries a second copy of this shell without the dispatch arm, and
    it also fires on `push: main` where the diff is likewise empty. It survives
    only because the step is gated to pull_request events. Dropping that gate
    reintroduces this exact red on every push to main.
    """
    step = _fence_step_run(".github/workflows/fences.yml", LIVE_CHECK_STEP)
    condition = str(step.get("if", ""))
    assert "pull_request" in condition and "github.event_name" in condition, (
        "fences.yml's live check must stay gated to pull_request events (or grow "
        f"the same verified-empty dispatch arm ci.yml has). Found if: {condition!r}"
    )
