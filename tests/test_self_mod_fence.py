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

from scripts.check_self_mod_fence import (
    changed_files_from_git,
    check,
    selftest,
    IMMUTABLE_PATTERNS,
    LOOP_BRANCH_PREFIXES,
    parse_ci_changed_files_json,
    print_planner_files,
    read_ci_changed_files_file,
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
        "scripts/audit_unrun_tests.py",
        "scripts/check_capability_redline.py",
        "scripts/check_ci_trigger_closure.py",
        "scripts/check_conflict_markers.py",
        "scripts/check_workflow_yaml.py",
        "scripts/ci_cancelled_run_completion.py",
        "scripts/ci_collect_pack_evidence.py",
        "scripts/ci_committed_scope_index.py",
        "scripts/ci_failure_summary.py",
        "scripts/ci_scope_dependencies.py",
        "scripts/ci_structural_preflight.py",
        "scripts/merge_on_green.py",
        "scripts/run_ci_pack.py",
        "scripts/workflow_run_source.py",
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
    job_id = (
        "fence-evaluation"
        if workflow_relpath.endswith("/fences.yml")
        else "self-mod-fence"
    )
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


def test_fences_workflow_live_check_covers_pr_and_merge_group_but_not_push():
    """The live diff exists for review and queue events, never a bare main push.

    Native merge queue requires the synthetic latest-main commit to repeat this
    fence. A main push has no review diff and must retain the selftest-only path.
    """
    step = _fence_step_run(".github/workflows/fences.yml", LIVE_CHECK_STEP)
    condition = str(step.get("if", ""))
    assert "github.event_name == 'pull_request'" in condition
    assert "github.event_name == 'merge_group'" in condition
    assert "push" not in condition
    body = str(step["run"])
    base_source = step["env"]["SELF_MOD_BASE_SHA"]
    assert "github.event.pull_request.base.sha" in base_source
    assert "github.event.merge_group.base_sha" in base_source
    assert "github.head_ref" not in body
    assert "SELF_MOD_HEAD_REF" in step["env"]
    assert "--base-sha" in body
    assert "--files " not in body
    assert "--name-only" not in body


def test_packed_live_check_reads_ci_changed_files_json():
    """After #5564 the packed fence must not require origin/main...HEAD."""
    step = _fence_step_run(".github/ci/legacy-jobs.yml", LIVE_CHECK_STEP)
    body = str(step["run"])
    assert "--print-planner-files" in body
    assert "--planner-files" in body
    assert '"${FILE_SOURCE[@]}"' in body
    assert "--files " not in body
    assert "${{ github.head_ref }}" not in body
    assert 'BRANCH="${CI_HEAD_REF:-}"' in body
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
    path.write_text('["a.py","b.md"]', encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("ok", ["a.py", "b.md"])
    path.write_text('["a.py","","b.md"]', encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("malformed", [])
    path.write_text("null", encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("ok", [])
    path.write_text("   ", encoding="utf-8")
    assert read_ci_changed_files_file(str(path)) == ("malformed", []), (
        "an empty handle is a transport that lost its payload, not an absent one"
    )


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


def test_live_check_option_like_filename_cannot_override_loop_branch(tmp_path):
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "metabolism/argv-injection", cwd=work)
    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="metabolism/argv-injection",
        extra_env={
            "CI_CHANGED_FILES_JSON": (
                '["--branch","human/override","scripts/run_ci_pack.py"]'
            )
        },
    )
    assert result.returncode != 0
    assert "BLOCKED" in result.stderr


def test_live_check_hostile_branch_name_is_data_not_shell(tmp_path):
    work = _seed_repo(tmp_path)
    hostile = 'metabolism/evil";exit${IFS}0;#x'
    _git("checkout", "-b", hostile, cwd=work)
    (work / ".github/workflows").mkdir(parents=True, exist_ok=True)
    (work / ".github/workflows/ci.yml").write_text("jobs: {}\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "hostile ref edits immutable workflow", cwd=work)

    result = _run_live_check(work, event="pull_request", head_ref=hostile)

    assert result.returncode != 0
    assert "BLOCKED" in result.stderr


def test_git_file_source_preserves_immutable_side_of_rename(tmp_path, monkeypatch):
    work = _seed_repo(tmp_path)
    _git("checkout", "-b", "metabolism/rename-fence", cwd=work)
    _git(
        "mv",
        "scripts/check_self_mod_fence.py",
        "scripts/ordinary_name.py",
        cwd=work,
    )
    _git("commit", "-m", "rename immutable authority away", cwd=work)

    monkeypatch.chdir(work)
    changed = changed_files_from_git("main")
    assert changed == [
        "scripts/check_self_mod_fence.py",
        "scripts/ordinary_name.py",
    ]
    rc, message = check("metabolism/rename-fence", changed)
    assert rc == 1
    assert "scripts/check_self_mod_fence.py" in message

    result = _run_live_check(
        work,
        event="pull_request",
        head_ref="metabolism/rename-fence",
    )
    assert result.returncode != 0
    assert "scripts/check_self_mod_fence.py" in result.stderr
