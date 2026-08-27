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

import errno
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.check_self_mod_fence import (
    check,
    selftest,
    IMMUTABLE_PATTERNS,
    LOOP_BRANCH_PREFIXES,
    parse_ci_changed_files_json,
    print_planner_files,
    read_ci_changed_files_file,
    read_trailers_file,
    write_ci_changed_files_file_from_nul,
)
from scripts.run_ci_pack import render_command


@pytest.fixture(autouse=True)
def _isolate_planner_transports(monkeypatch: pytest.MonkeyPatch) -> None:
    """This suite runs INSIDE a pack, which exports the live PR's diff.

    Both transport names must go, and the FILE one especially: it out-ranks the
    inline value, so isolating only ``CI_CHANGED_FILES_JSON`` would leave
    ``print_planner_files`` answering from the hosted runner's own artifact —
    the #5560 leak class, where a pack's ambient planner state made unrelated
    PRs red. Tests that need a transport set one explicitly.
    """
    for name in ("CI_CHANGED_FILES_FILE", "CI_CHANGED_FILES_JSON"):
        monkeypatch.delenv(name, raising=False)


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
FENCE_SCRIPT = REPO_ROOT / "scripts" / "check_self_mod_fence.py"


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
    shutil.copy2(
        REPO_ROOT / "scripts/ci_authority_paths.py",
        work / "scripts/ci_authority_paths.py",
    )
    (work / "README.md").write_text("base\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "base", cwd=work)
    _git("push", "origin", "main", cwd=work)
    return work


def _run_live_check(
    work: Path,
    *,
    event: str,
    head_ref: str,
    base_ref: str = "main",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Render the manifest step exactly as ci-pack does, then run it."""
    command = render_command(
        str(_fence_step_run(".github/ci/legacy-jobs.yml", LIVE_CHECK_STEP)["run"]),
        base_ref=base_ref,
        head_ref=head_ref,
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    # Pack jobs export the planner's list — as a FILE handle since 2026-08-14,
    # inline before that. These tests seed their own git history; inheriting the
    # pack runner's list would skip the git fallback the historical cases pin,
    # and the file name must be popped too or the same leak returns wearing a
    # different variable.
    env.pop("CI_CHANGED_FILES_FILE", None)
    env.pop("CI_CHANGED_FILES_JSON", None)
    env.pop("GITHUB_HEAD_REF", None)
    env["GITHUB_EVENT_NAME"] = event
    env["CI_HEAD_REF"] = head_ref
    if extra_env:
        env.update(extra_env)
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


def test_live_check_uses_event_head_ref_when_renderer_head_ref_is_empty(tmp_path):
    """A main-owned pre-upgrade executor must retain the PR's branch identity.

    Reusable workflow control is deliberately loaded from ``main``, so the PR that
    introduces ``CI_HEAD_REF`` cannot use that new wiring to prove itself. GitHub's
    pull-request environment still carries ``GITHUB_HEAD_REF`` into the sealed pack
    child. A human branch touching an immutable path must therefore classify as human,
    not fail closed as an empty/unclassifiable branch during that one-head bootstrap.
    """
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "human/fence-repair", cwd=work)
    (work / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (work / ".github/workflows/ci.yml").write_text("jobs: {}\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "human repairs an immutable path", cwd=work)

    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="",
        extra_env={"GITHUB_HEAD_REF": "human/fence-repair"},
    )
    assert result.returncode == 0, (
        "the pull-request event branch must bridge a pre-upgrade main executor.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "PASS: branch 'human/fence-repair'" in result.stdout


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


def test_packed_live_check_reads_ci_changed_files_json():
    """After #5564 the packed fence must not require origin/main...HEAD."""
    step = _fence_step_run(".github/ci/legacy-jobs.yml", LIVE_CHECK_STEP)
    body = str(step["run"])
    assert "--print-planner-files" in body
    # Both transports by name (2026-08-14): the list moved to a FILE because
    # the inline form E2BIG'd every pack at launch, and an operator reading
    # this failure needs to know which of the two to go and look at.
    assert "CI_CHANGED_FILES_FILE/CI_CHANGED_FILES_JSON malformed" in body


@pytest.mark.parametrize(
    "raw,status,paths",
    [
        (None, "unset", []),
        ("", "unset", []),
        ("null", "ok", []),
        ('["engine/a.py","docs/b.md"]', "ok", ["engine/a.py", "docs/b.md"]),
        ("{nope}", "malformed", []),
        ("[1, 2]", "malformed", []),
        ('"engine/a.py"', "malformed", []),
    ],
)
def test_parse_ci_changed_files_json(raw, status, paths):
    got_status, got_paths = parse_ci_changed_files_json(raw)
    assert (got_status, got_paths) == (status, paths)


def test_print_planner_files_exit_codes(monkeypatch, capsys):
    monkeypatch.delenv("CI_CHANGED_FILES_JSON", raising=False)
    assert print_planner_files() == 3
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", "{nope}")
    assert print_planner_files() == 2
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", "null")
    assert print_planner_files() == 0
    assert capsys.readouterr().out == ""
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["a.py","b.md"]')
    assert print_planner_files() == 0
    assert capsys.readouterr().out == "a.py\nb.md"


def test_print_planner_files_reads_the_file_before_the_env(tmp_path, monkeypatch, capsys):
    """The 2026-08-14 transport, and its exact exit-code contract.

    The list moved out of the process environment because 350,264 bytes of
    paths met execve's 131,072-byte MAX_ARG_STRLEN and killed every pack at
    launch (run 31775693780). Two properties the packed shell depends on:

      * FILE WINS. A pack downloads the artifact and exports the handle; a
        stale inline string from an older step must not out-vote it, or the
        fence classifies a diff nobody published.
      * A configured-but-broken file is exit 2, NEVER exit 3. Exit 3 licenses
        the shell's git fallback, and answering "no list published" for a
        transport that lost its payload is precisely the fail-open R-AUT-5
        forbids — on a depth-1 pack the git fallback then finds nothing and the
        fence would pass a loop PR it never classified.
    """
    monkeypatch.delenv("CI_CHANGED_FILES_JSON", raising=False)
    handle = tmp_path / "changed-files.json"
    handle.write_text('[".github/workflows/ci.yml","docs/存档 note.md"]', encoding="utf-8")
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(handle))
    assert print_planner_files() == 0
    assert capsys.readouterr().out == ".github/workflows/ci.yml\ndocs/存档 note.md"

    # The file out-ranks a contradicting inline value.
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["engine/decoy.py"]')
    assert print_planner_files() == 0
    assert capsys.readouterr().out == ".github/workflows/ci.yml\ndocs/存档 note.md"

    handle.write_text("null", encoding="utf-8")
    assert print_planner_files() == 0
    assert capsys.readouterr().out == ""

    for broken in ("{nope", "", '"one string"'):
        handle.write_text(broken, encoding="utf-8")
        assert print_planner_files() == 2, f"{broken!r} must fail closed, not fall back"

    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(tmp_path / "never-written.json"))
    assert print_planner_files() == 2

    # Unset handle: the inline path is untouched, and exit 3 (git fallback)
    # only when NEITHER transport is configured.
    monkeypatch.delenv("CI_CHANGED_FILES_FILE")
    assert print_planner_files() == 0
    assert capsys.readouterr().out == "engine/decoy.py"
    monkeypatch.delenv("CI_CHANGED_FILES_JSON")
    assert print_planner_files() == 3


def test_read_ci_changed_files_file_statuses(tmp_path):
    """The decoder's three statuses, including the one that must not be `unset`."""
    assert read_ci_changed_files_file(None) == ("unset", [])
    assert read_ci_changed_files_file("") == ("unset", [])
    assert read_ci_changed_files_file(str(tmp_path / "absent.json")) == ("malformed", [])
    path = tmp_path / "changed-files.json"
    path.write_text('["a.py","","b.md"]', encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("ok", ["a.py", "b.md"])
    path.write_text("null", encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("ok", [])
    path.write_text("   ", encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("malformed", []), (
        "an empty handle is a transport that lost its payload, not an absent one"
    )


def test_nul_git_paths_write_the_canonical_json_transport(tmp_path):
    """The workflow producer preserves path boundaries without shell splitting."""
    destination = tmp_path / "nested" / "changed-files.json"
    paths = [
        "docs/name with spaces.md",
        "docs/研究/季度报告 — α.md",
        "docs/name-with-a-newline\ncontinued.md",
    ]
    raw = b"\0".join(os.fsencode(path) for path in paths) + b"\0"
    assert write_ci_changed_files_file_from_nul(str(destination), raw) == 0
    assert read_ci_changed_files_file(str(destination)) == ("ok", paths)


def test_nul_git_path_writer_fails_closed_on_a_truncated_stream(tmp_path, capsys):
    destination = tmp_path / "changed-files.json"
    assert write_ci_changed_files_file_from_nul(
        str(destination), b"docs/not-terminated.md"
    ) == 1
    assert "fail-closed" in capsys.readouterr().err
    assert not destination.exists()


def test_trailer_file_distinguishes_valid_empty_from_broken_transport(tmp_path):
    trailers = tmp_path / "commit-messages.txt"
    trailers.write_text("", encoding="utf-8")
    assert read_trailers_file(str(trailers)) == ("ok", "")
    assert read_trailers_file(str(tmp_path / "absent.txt")) == ("malformed", "")
    trailers.write_bytes(b"\xff")
    assert read_trailers_file(str(trailers)) == ("malformed", "")


def test_live_check_uses_the_planner_file_without_origin_main(tmp_path):
    """The packed shell end-to-end on the file transport (2026-08-14).

    Same hole #5556/#5519/#5499 opened — fetch-depth:1, `origin/main...HEAD` is
    a bad revision — now closed by a handle instead of an env string, because
    the env string could not be delivered at all once a PR's diff grew past
    execve's per-string cap.
    """
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "claude/human-docs", cwd=work)
    (work / "note.md").write_text("docs\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "docs", cwd=work)
    _git("remote", "remove", "origin", cwd=work)
    handle = tmp_path / "changed-files.json"
    handle.write_text('["note.md"]', encoding="utf-8")

    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="claude/human-docs",
        extra_env={"CI_CHANGED_FILES_FILE": str(handle)},
    )
    assert result.returncode == 0, (
        "the published FILE must classify a human PR even when origin/main is "
        f"missing.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "PASS" in result.stdout


def test_live_check_malformed_planner_file_fail_closed(tmp_path):
    """A broken handle blocks; it must not silently become a git fallback."""
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "claude/human-docs", cwd=work)
    handle = tmp_path / "changed-files.json"
    handle.write_text("{nope", encoding="utf-8")
    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="claude/human-docs",
        extra_env={"CI_CHANGED_FILES_FILE": str(handle)},
    )
    assert result.returncode == 1
    assert "malformed" in result.stderr


def test_live_check_planner_file_still_blocks_loop_plus_immutable(tmp_path):
    """The fence's whole job must survive the transport change."""
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "metabolism/self-edit", cwd=work)
    (work / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (work / ".github/workflows/ci.yml").write_text("jobs: {}\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "loop edits an immutable path", cwd=work)
    _git("remote", "remove", "origin", cwd=work)
    handle = tmp_path / "changed-files.json"
    handle.write_text('[".github/workflows/ci.yml"]', encoding="utf-8")

    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="metabolism/self-edit",
        extra_env={"CI_CHANGED_FILES_FILE": str(handle)},
    )
    assert result.returncode != 0
    assert "BLOCKED" in result.stderr


def test_live_check_uses_planner_json_without_origin_main(tmp_path):
    """The #5556/#5519/#5499 hole: fetch-depth:1, origin/main...HEAD is a bad revision.

    ci-plan already listed the files. The fence must classify those, not fail-closed.
    """
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "claude/human-docs", cwd=work)
    (work / "note.md").write_text("docs\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "docs", cwd=work)
    _git("remote", "remove", "origin", cwd=work)

    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="claude/human-docs",
        extra_env={"CI_CHANGED_FILES_JSON": '["note.md"]'},
    )
    assert result.returncode == 0, (
        "planner JSON must classify a human PR even when origin/main is missing.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "PASS" in result.stdout


def test_live_check_malformed_planner_json_fail_closed(tmp_path):
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "claude/human-docs", cwd=work)
    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="claude/human-docs",
        extra_env={"CI_CHANGED_FILES_JSON": "{nope"},
    )
    assert result.returncode == 1
    assert "malformed" in result.stderr


def test_live_check_null_planner_json_is_verified_empty(tmp_path):
    """Well-formed null from ci-plan is determined-empty, not unclassifiable."""
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "claude/empty", cwd=work)
    _git("remote", "remove", "origin", cwd=work)
    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="claude/empty",
        extra_env={"CI_CHANGED_FILES_JSON": "null"},
    )
    assert result.returncode == 0, (
        "null JSON must pass (ci-plan already classified the diff).\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ci-plan reported no changed files" in result.stdout


def test_live_check_planner_json_still_blocks_loop_plus_immutable(tmp_path):
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "metabolism/self-edit", cwd=work)
    (work / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (work / ".github/workflows/ci.yml").write_text("jobs: {}\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "loop edits an immutable path", cwd=work)
    _git("remote", "remove", "origin", cwd=work)

    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="metabolism/self-edit",
        extra_env={"CI_CHANGED_FILES_JSON": '[".github/workflows/ci.yml"]'},
    )
    assert result.returncode != 0
    assert "BLOCKED" in result.stderr


# ── 8. Required-fence E2BIG transport closure (PR #5898 / run 32546500471) ──

_E2BIG_MIN_PAYLOAD_BYTES = 2_000_000


@pytest.fixture(scope="module")
def oversized_fence_inputs(tmp_path_factory):
    """Two independently unbounded populations, each larger than exec limits.

    The changed paths include the hostile pathname shapes from the canonical
    #5608 regression. The commit text simulates thousands of complete commit
    messages and places the discriminating trailer at the very end, so a
    truncating or prefix-only implementation cannot pass.
    """
    root = tmp_path_factory.mktemp("self-mod-e2big")
    paths = [
        f"docs/研究/{index:05d}/sector-rotation-quarterly-snapshot/"
        f"季度报告 {index} α — final draft.md"
        for index in range(18_000)
    ]
    immutable_paths = [".github/workflows/fences.yml", *paths[1:]]
    human_trailers = "\n\n".join(
        f"Synthetic commit {index}\n\nNoise-{index}: {'x' * 180}"
        for index in range(12_000)
    ) + "\n"
    loop_trailers = human_trailers + "Loop-Authored: e2big-regression\n"

    def write_paths(name: str, population: list[str]) -> tuple[Path, Path]:
        json_path = root / f"{name}.json"
        nul_path = root / f"{name}.nul"
        json_path.write_text(
            json.dumps(population, separators=(",", ":")), encoding="utf-8"
        )
        nul_path.write_bytes(
            b"\0".join(os.fsencode(path) for path in population) + b"\0"
        )
        return json_path, nul_path

    files_json, files_nul = write_paths("non-immutable-files", paths)
    immutable_json, immutable_nul = write_paths(
        "immutable-files", immutable_paths
    )
    human_trailers_file = root / "human-commit-messages.txt"
    loop_trailers_file = root / "loop-commit-messages.txt"
    human_trailers_file.write_text(human_trailers, encoding="utf-8")
    loop_trailers_file.write_text(loop_trailers, encoding="utf-8")

    assert files_json.stat().st_size > _E2BIG_MIN_PAYLOAD_BYTES
    assert len(human_trailers.encode("utf-8")) > _E2BIG_MIN_PAYLOAD_BYTES
    return {
        "root": root,
        "paths": paths,
        "immutable_paths": immutable_paths,
        "files_json": files_json,
        "files_nul": files_nul,
        "immutable_json": immutable_json,
        "immutable_nul": immutable_nul,
        "human_trailers": human_trailers,
        "loop_trailers": loop_trailers,
        "human_trailers_file": human_trailers_file,
        "loop_trailers_file": loop_trailers_file,
    }


def _run_file_backed_fence(
    *, branch: str, files_file: Path, trailers_file: Path
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(FENCE_SCRIPT),
            "--branch",
            branch,
            "--files-file",
            str(files_file),
            "--trailers-file",
            str(trailers_file),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="execve caps are POSIX")
def test_retired_argv_shape_reproduces_e2big(oversized_fence_inputs):
    """A real process launch reproduces the transport class Python never sees."""
    old_argv = [
        sys.executable,
        str(FENCE_SCRIPT),
        "--branch",
        "claude/human-looking",
        "--files",
        *oversized_fence_inputs["immutable_paths"],
        "--trailers",
        oversized_fence_inputs["loop_trailers"],
    ]
    with pytest.raises(OSError) as caught:
        subprocess.run(old_argv, cwd=REPO_ROOT, check=False)
    assert caught.value.errno == errno.E2BIG, (
        f"expected E2BIG from the retired argv transport, got {caught.value}"
    )


@pytest.mark.parametrize(
    "branch,immutable,loop_trailer",
    [
        ("claude/human-immutable", True, False),
        ("metabolism/loop-immutable", True, False),
        ("claude/trailer-loop-immutable", True, True),
        ("metabolism/loop-non-immutable", False, False),
    ],
)
def test_large_file_transport_launches_with_identical_classification(
    oversized_fence_inputs,
    branch,
    immutable,
    loop_trailer,
):
    """The repaired child starts and preserves every discriminating verdict."""
    paths = oversized_fence_inputs[
        "immutable_paths" if immutable else "paths"
    ]
    trailers = oversized_fence_inputs[
        "loop_trailers" if loop_trailer else "human_trailers"
    ]
    expected_rc, expected_message = check(
        branch=branch,
        changed_files=paths,
        trailers_text=trailers,
    )
    result = _run_file_backed_fence(
        branch=branch,
        files_file=oversized_fence_inputs[
            "immutable_json" if immutable else "files_json"
        ],
        trailers_file=oversized_fence_inputs[
            "loop_trailers_file" if loop_trailer else "human_trailers_file"
        ],
    )
    assert result.returncode == expected_rc, (
        f"file-backed fence changed classification or did not launch\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert expected_message in result.stdout + result.stderr


def test_file_backed_cli_fails_closed_on_empty_or_malformed_files(tmp_path):
    trailers = tmp_path / "trailers.txt"
    trailers.write_text("", encoding="utf-8")
    for index, raw in enumerate(("", "[]", "null", "{nope", '["",1]')):
        changed = tmp_path / f"changed-{index}.json"
        changed.write_text(raw, encoding="utf-8")
        result = _run_file_backed_fence(
            branch="claude/unclassifiable",
            files_file=changed,
            trailers_file=trailers,
        )
        assert result.returncode == 1, raw
        assert "fail-closed" in result.stderr

    valid_changed = tmp_path / "valid-changed.json"
    valid_changed.write_text('[".github/workflows/fences.yml"]', encoding="utf-8")
    for broken in (tmp_path / "absent.txt", tmp_path / "invalid.txt"):
        if broken.name == "invalid.txt":
            broken.write_bytes(b"\xff")
        result = _run_file_backed_fence(
            branch="claude/unclassifiable",
            files_file=valid_changed,
            trailers_file=broken,
        )
        assert result.returncode == 1
        assert "fail-closed" in result.stderr


def test_file_backed_cli_accepts_a_valid_empty_trailer_file(tmp_path):
    changed = tmp_path / "changed.json"
    changed.write_text('[".github/workflows/fences.yml"]', encoding="utf-8")
    trailers = tmp_path / "trailers.txt"
    trailers.write_text("", encoding="utf-8")
    result = _run_file_backed_fence(
        branch="claude/human-immutable",
        files_file=changed,
        trailers_file=trailers,
    )
    assert result.returncode == 0
    assert "human/operator PR" in result.stdout


def test_file_backed_cli_rejects_ambiguous_inline_and_file_inputs(tmp_path):
    changed = tmp_path / "changed.json"
    changed.write_text('["docs/a.md"]', encoding="utf-8")
    trailers = tmp_path / "trailers.txt"
    trailers.write_text("", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(FENCE_SCRIPT),
            "--branch",
            "claude/ambiguous",
            "--files-file",
            str(changed),
            "--files",
            "docs/b.md",
            "--trailers-file",
            str(trailers),
            "--trailers",
            "Loop-Authored: decoy",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "ambiguous input" in result.stderr


def _fences_live_step(job_id: str) -> dict:
    payload = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/fences.yml").read_text(encoding="utf-8")
    )
    steps = payload["jobs"][job_id]["steps"]
    matches = [step for step in steps if step.get("name") == LIVE_CHECK_STEP]
    assert len(matches) == 1
    return matches[0]


def _fake_git_for_fences(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  rev-list)
    printf '%s %s %s\\n' "$FAKE_GIT_MERGE_SHA" "$FAKE_GIT_BASE_SHA" "$FAKE_GIT_HEAD_SHA"
    ;;
  merge-base)
    if [ "${FAKE_GIT_FAIL_MERGE_BASE:-0}" = "1" ]; then exit 1; fi
    printf '%s\\n' "$FAKE_GIT_BASE_SHA"
    ;;
  log)
    cat "$FAKE_GIT_TRAILERS_FILE"
    ;;
  diff)
    cat "$FAKE_GIT_FILES_NUL_FILE"
    ;;
  fetch)
    exit 0
    ;;
  *)
    printf 'unexpected fake git invocation: %s\\n' "$*" >&2
    exit 93
    ;;
esac
""",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    return fake_bin


def _run_fences_workflow_live_step(
    tmp_path: Path,
    *,
    job_id: str,
    branch: str,
    files_nul: Path,
    trailers_file: Path,
    fail_merge_base: bool = False,
) -> subprocess.CompletedProcess:
    command = render_command(
        str(_fences_live_step(job_id)["run"]),
        base_ref="main",
        head_ref=branch,
    )
    fake_bin = _fake_git_for_fences(tmp_path)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "RUNNER_TEMP": str(tmp_path / "runner-temp"),
            "GITHUB_SHA": "synthetic-merge",
            "FAKE_GIT_MERGE_SHA": "synthetic-merge",
            "FAKE_GIT_BASE_SHA": "tested-base",
            "FAKE_GIT_HEAD_SHA": "subject-head",
            "FAKE_GIT_FILES_NUL_FILE": str(files_nul),
            "FAKE_GIT_TRAILERS_FILE": str(trailers_file),
            "FAKE_GIT_FAIL_MERGE_BASE": "1" if fail_merge_base else "0",
        }
    )
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", command],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("job_id", ["fence-pack", "fork-self-mod-fence"])
def test_real_workflow_paths_launch_with_both_large_populations(
    tmp_path,
    oversized_fence_inputs,
    job_id,
):
    """Both production copies reach policy evaluation with oversized inputs."""
    result = _run_fences_workflow_live_step(
        tmp_path,
        job_id=job_id,
        branch="claude/human-looking",
        files_nul=oversized_fence_inputs["immutable_nul"],
        trailers_file=oversized_fence_inputs["loop_trailers_file"],
    )
    assert result.returncode == 1
    assert "Loop-Authored: commit trailer" in result.stderr, (
        "the real workflow must launch the checker and classify the complete "
        f"large payload\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_bounded_checkout_ancestry_failure_remains_fail_closed(
    tmp_path,
    oversized_fence_inputs,
):
    result = _run_fences_workflow_live_step(
        tmp_path,
        job_id="fence-pack",
        branch="claude/human-looking",
        files_nul=oversized_fence_inputs["immutable_nul"],
        trailers_file=oversized_fence_inputs["human_trailers_file"],
        fail_merge_base=True,
    )
    assert result.returncode == 1
    assert (
        "could not establish exact PR ancestry inside the bounded checkout"
        in result.stderr
    )
