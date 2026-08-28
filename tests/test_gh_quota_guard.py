"""Tests for .claude/hooks/gh_quota_guard.py (PreToolUse shared-quota guard).

THE INCIDENT THIS ENCODES (2026-07-26). `gh` authenticates as ONE account token,
so REST's 5,000/hr `core` pool is a single bucket shared by every parallel
session, the babysitter lane, and the hooks. A session ran three 10-minute
`gh run watch` windows (gh's default interval is 3s, and each poll fetches the
run AND its ~130 jobs) on top of a background chain already polling the same run
every 45s, and emptied the pool — 403ing every other session for ~5 minutes,
including ship_loop_guard.py, which spends up to four REST calls per Stop and
FAILS CLOSED when rate-limited.

A memory note describing exactly this already existed; a second session hit it an
hour later anyway. Hence a hook: the deny matrix below IS the contract.

Runs the hook as a subprocess exactly as the harness does (JSON payload on
stdin). Contract: exit 0 always; a DENY prints hookSpecificOutput with
permissionDecision == "deny"; an ALLOW prints nothing.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "gh_quota_guard.py"

# In-process handle on the same file, for the ONE thing a subprocess cannot pin:
# that a command outside the guard's business spawns no probe at all. Everything
# else in this file still goes through the real stdin/stdout hook boundary.
_HOOK_SPEC = importlib.util.spec_from_file_location("gh_quota_guard", HOOK)
assert _HOOK_SPEC and _HOOK_SPEC.loader
GUARD = importlib.util.module_from_spec(_HOOK_SPEC)
_HOOK_SPEC.loader.exec_module(GUARD)

# ─────────────────────────────────────────────────────────────────────────────
# No test in this file may reach api.github.com
# ─────────────────────────────────────────────────────────────────────────────
#
# Deny shape 4 (2026-08-09) PROBES: the guard shells out to `gh run list` before
# it can judge a `gh workflow run ci.yml --ref main`. Left unstubbed that is a real
# REST call from the test suite — against the very shared pool this hook protects —
# and it would make the verdict depend on whether main happened to have a run in
# flight while CI was running. So `gh` itself is replaced on PATH, at the process
# boundary the hook actually uses. The default payload is "no runs at all", which is
# the pre-2026-08-09 behaviour: every older test in this file keeps its old answer.

_SHIM = """#!{python}
import os, sys
code = int(os.environ.get("GH_SHIM_EXIT", "0"))
if code:
    sys.stderr.write(os.environ.get("GH_SHIM_STDERR", "HTTP 403: rate limit exceeded"))
    sys.exit(code)
sys.stdout.write(os.environ.get("GH_SHIM_PAYLOAD", "[]"))
"""


@pytest.fixture(autouse=True)
def _gh_shim(tmp_path_factory, monkeypatch):
    shim_dir = tmp_path_factory.mktemp("ghshim")
    gh = shim_dir / "gh"
    gh.write_text(_SHIM.format(python=sys.executable), encoding="utf-8")
    gh.chmod(0o755)
    # Prepending to os.environ is what reaches the hook: the guard runs as a
    # subprocess and inherits this PATH.
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("GH_SHIM_EXIT", raising=False)
    monkeypatch.setenv("GH_SHIM_PAYLOAD", "[]")


def _stamp(minutes_ago: float) -> str:
    """RELATIVE to the wall clock on purpose — a frozen literal would age past the
    40-minute orphan bound and silently flip these tests at some future date."""
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _runs(monkeypatch, *runs: dict) -> None:
    monkeypatch.setenv("GH_SHIM_PAYLOAD", json.dumps(list(runs)))


def _run_row(status: str, minutes_ago: float = 2, run_id: int = 31309720615) -> dict:
    return {
        "status": status,
        "createdAt": _stamp(minutes_ago),
        "databaseId": run_id,
        "url": f"https://example.test/run/{run_id}",
    }


def _raw(cmd: str, tool: str = "Bash", cwd=None) -> subprocess.CompletedProcess:
    payload: dict = {"tool_name": tool, "tool_input": {"command": cmd}}
    if cwd is not None:
        payload["cwd"] = str(cwd)          # the harness names the invoking checkout
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=30,
    )


def _run(cmd: str, tool: str = "Bash", cwd=None) -> dict | None:
    proc = _raw(cmd, tool, cwd)
    assert proc.returncode == 0, "the guard must never brick the harness"
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out:
        return None
    return json.loads(out).get("hookSpecificOutput")


def _denied(cmd: str, cwd=None) -> bool:
    d = _run(cmd, cwd=cwd)
    return bool(d and d.get("permissionDecision") == "deny")


# ─────────────────────────────────────────────────────────────────────────────
# The burn, verbatim
# ─────────────────────────────────────────────────────────────────────────────

def test_the_exact_command_that_emptied_the_pool_is_denied():
    """Run three of these and the shared 5,000/hr core pool is gone."""
    assert _denied("gh run watch 30218680958 --exit-status --compact")


def test_gh_run_watch_default_interval_is_the_trap():
    """gh's default is --interval 3. Nothing in the command line says so, which
    is exactly why it slipped through review."""
    assert _denied("gh run watch 302186")
    assert _denied("gh run watch 302186 -i 3")
    assert _denied("gh run watch 302186 --interval 30")
    assert _denied("gh run view 302186 --watch")


def test_a_slow_explicit_interval_is_allowed():
    """The guard throttles; it does not ban the tool."""
    assert not _denied("gh run watch 302186 --interval 60")
    assert not _denied("gh run watch 302186 --interval 150")
    assert not _denied("gh run watch 302186 -i 300")


# ─────────────────────────────────────────────────────────────────────────────
# Poll loops
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sleep_s", [5, 30, 40, 45, 60, 89])
def test_gh_poll_loops_under_the_floor_are_denied(sleep_s):
    """Two watchers on one endpoint at 45s took 4,488 -> 0 in under an hour."""
    assert _denied(
        f"until [ x = y ]; do gh api repos/o/r/actions/runs/1; sleep {sleep_s}; done")


@pytest.mark.parametrize("sleep_s", [90, 150, 300])
def test_gh_poll_loops_at_or_above_the_floor_are_allowed(sleep_s):
    assert not _denied(
        f"until [ x = y ]; do gh api repos/o/r/actions/runs/1; sleep {sleep_s}; done")


def test_a_loop_with_no_sleep_at_all_is_denied():
    assert _denied("while true; do gh api rate_limit; done")


def test_a_loop_without_gh_is_none_of_the_guards_business():
    assert not _denied("for f in a b c; do echo $f; sleep 1; done")
    assert not _denied("until [ -s out.txt ]; do sleep 5; done")


# ─────────────────────────────────────────────────────────────────────────────
# --paginate over check-runs
# ─────────────────────────────────────────────────────────────────────────────

def test_paginate_over_check_runs_is_denied_either_argument_order():
    assert _denied('gh api "repos/o/r/commits/$SHA/check-runs?per_page=100" --paginate')
    assert _denied('gh api --paginate "repos/o/r/actions/runs/1/jobs"')


def test_a_single_page_of_jobs_is_allowed():
    """One page already answers 'is it still running'."""
    assert not _denied('gh api "repos/o/r/actions/runs/1/jobs?per_page=60"')


# ─────────────────────────────────────────────────────────────────────────────
# Ordinary work must not be impeded
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "gh pr view 3748 --json state,mergedAt",
    "gh pr merge 3748 --squash --delete-branch",
    "gh pr create --title x --body y",
    "gh workflow run ci.yml --ref main",
    "gh api rate_limit --jq '.resources.core.remaining'",
    "gh api repos/o/r/actions/runs/1 --jq '.status'",
    "gh run rerun --failed 302186",
    "git log --oneline -3",
    "python -m pytest tests/ -q",
])
def test_ordinary_commands_pass(cmd):
    assert not _denied(cmd)


def test_non_bash_tools_are_ignored():
    assert _denied("gh run watch 1"), "control: this command IS denied on Bash"
    d = _run("gh run watch 1", tool="Edit")
    assert d is None, "the guard only inspects Bash"


def test_the_denial_explains_the_shared_pool_and_gives_the_pattern():
    """A guard that only says no teaches nothing — the next session repeats it."""
    d = _run("gh run watch 302186")
    reason = (d or {}).get("permissionDecisionReason", "")
    assert "shared" in reason.lower() or "every session" in reason.lower()
    assert "rate_limit" in reason, "must show the preflight call"
    assert "ship_loop_guard" in reason, "must name the self-inflicted bite"


def test_guard_fails_open_on_garbage_input():
    """A guard that bricks the harness is worse than a missed warning."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=b"not json at all",
        capture_output=True, timeout=10)
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == ""


# ─────────────────────────────────────────────────────────────────────────────
# Writing ABOUT the trap must stay legal
# ─────────────────────────────────────────────────────────────────────────────
#
# Caught in production the first minute this hook was live: it denied the very
# commit that introduced it, because the commit message documents `gh run watch`.
# A guard that blocks its own postmortem is worse than no guard.

def test_a_commit_message_documenting_the_trap_is_not_denied():
    cmd = (
        "git commit -q -F - <<'MSG'\n"
        "fix(hooks): guard the shared GitHub quota\n\n"
        "A session ran three 10-minute `gh run watch` windows on top of a chain\n"
        "already polling every 45s. gh run watch defaults to --interval 3.\n"
        "MSG\n"
        "git push -q -u origin HEAD"
    )
    assert not _denied(cmd)


def test_prose_and_comments_mentioning_gh_run_watch_are_not_invocations():
    assert not _denied("echo 'never use gh run watch here'")
    assert not _denied("# gh run watch is banned; use a 150s loop")
    assert not _denied('git commit -m "drop gh run watch from the babysitter"')


def test_a_real_invocation_after_a_heredoc_is_still_caught():
    """Stripping heredocs must not blind the guard to the command beside them."""
    cmd = ("git commit -F - <<'MSG'\nsome message body\nMSG\n"
           "gh run watch 302186")
    assert _denied(cmd)


def test_heredoc_stripping_survives_two_heredocs():
    cmd = ("cat <<'A'\ngh run watch 1\nA\ncat <<'B'\ngh run watch 2\nB\necho done")
    assert not _denied(cmd)


# ─────────────────────────────────────────────────────────────────────────────
# A loop must actually CONTAIN the gh call
# ─────────────────────────────────────────────────────────────────────────────
#
# Second production false positive, minutes after the first: a verification
# command with `python3 -c "for m in ...: print(...)"` and an unrelated
# `gh api rate_limit` on the same line was denied as a "poll loop". Co-presence
# of a loop keyword and a gh call is not polling.

def test_a_python_for_loop_beside_an_unrelated_gh_call_is_not_a_poll_loop():
    cmd = (
        "git show origin/main:.claude/settings.json | python3 -c \""
        "import json,sys\n"
        "d=json.load(sys.stdin)\n"
        "for m in d['hooks']['PreToolUse']:\n"
        "    for h in m['hooks']: print(h)\n"
        "\"; gh api rate_limit --jq '.resources.core.remaining'"
    )
    assert not _denied(cmd)


def test_a_list_comprehension_beside_a_gh_call_is_not_a_poll_loop():
    assert not _denied(
        """python3 -c "print([x for x in range(3)])" && gh pr view 3797 --json state""")


def test_a_real_shell_loop_around_gh_is_still_caught():
    """The narrowing must not blind the guard to actual polling."""
    assert _denied("while true; do gh api repos/o/r/actions/runs/1; sleep 20; done")
    assert _denied("for i in $(seq 1 40); do gh pr checks 1; sleep 30; done")


def test_a_shell_loop_whose_body_has_no_gh_is_ignored_even_beside_gh():
    cmd = ("for f in a b c; do echo $f; sleep 1; done; "
           "gh api rate_limit --jq '.resources.core.remaining'")
    assert not _denied(cmd)


# ─────────────────────────────────────────────────────────────────────────────
# Shape 4: dispatching a main proof over one already in flight (2026-08-09)
# ─────────────────────────────────────────────────────────────────────────────
#
# THE LIVELOCK THIS ENCODES. ci.yml has no `push` trigger, so main is proven only
# by a workflow_dispatch, and every main-ref dispatch shares `ci-refs/heads/main`.
# With the flat `cancel-in-progress: true` that group had until this change, each
# pinned session re-firing the documented recovery lever KILLED the proof already
# running: run 31309720615 was cancelled 44 minutes in by dispatch 31311537537,
# itself cancelled 4 minutes later by 31311693575. No proof concluded, the
# sweeper's base-inherited-red refresh stayed closed, and 12 merge-blocked + 56
# cap-deferred pull requests could not drain (sweep run 31311549150).
#
# The workflows are fenced now, so a race is waste rather than destruction — but
# the reflex is what opened the wound, and waste on a 4-job 30-34 minute run is
# worth one REST call to prevent.

@pytest.mark.parametrize("workflow", ["ci.yml", "fences.yml", "integration-baseline.yml"])
def test_dispatching_a_proof_over_a_live_one_is_denied(monkeypatch, workflow):
    _runs(monkeypatch, _run_row("in_progress"))
    assert _denied(f"gh workflow run {workflow} --ref main")


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "requested"])
def test_every_non_completed_status_counts_as_in_flight(monkeypatch, status):
    """`status != completed` is the test, not a list of the two statuses someone
    remembered — `waiting` and `requested` are exactly what an earlier revision of
    merge_on_green's anti-stampede query missed."""
    _runs(monkeypatch, _run_row(status, minutes_ago=3))
    assert _denied("gh workflow run ci.yml --ref main")


def test_a_dispatch_with_no_live_run_is_the_documented_recovery_lever(monkeypatch):
    """The guard must not stand between a stale main and its fix."""
    _runs(monkeypatch,
          _run_row("completed", minutes_ago=30),
          _run_row("completed", minutes_ago=90, run_id=31148430602))
    assert not _denied("gh workflow run ci.yml --ref main")
    assert not _denied("gh workflow run ci.yml")          # no --ref: gh defaults to main


def test_no_runs_at_all_is_allowed(monkeypatch):
    _runs(monkeypatch)
    assert not _denied("gh workflow run ci.yml --ref main")


def test_an_orphaned_queued_run_may_be_dispatched_over(monkeypatch):
    """A queued run that never starts would otherwise block the lever forever."""
    _runs(monkeypatch, _run_row("queued", minutes_ago=95))
    assert not _denied("gh workflow run ci.yml --ref main")


def test_a_freshly_queued_run_is_not_an_orphan(monkeypatch):
    """Control for the mercy kill: the escape valve must not swallow the rule."""
    _runs(monkeypatch, _run_row("queued", minutes_ago=5))
    assert _denied("gh workflow run ci.yml --ref main")


def test_a_long_running_run_is_not_an_orphan(monkeypatch):
    """Only `queued` ages out. A run holding a runner for 95 minutes is the
    evidence being waited on — killing it is the livelock itself."""
    _runs(monkeypatch, _run_row("in_progress", minutes_ago=95))
    assert _denied("gh workflow run ci.yml --ref main")


def test_the_newest_in_flight_run_decides(monkeypatch):
    """An old completed run beside a live one must not read as 'free'."""
    _runs(monkeypatch,
          _run_row("in_progress", minutes_ago=4, run_id=31311537537),
          _run_row("completed", minutes_ago=200))
    d = _run("gh workflow run ci.yml --ref main")
    assert d and d.get("permissionDecision") == "deny"
    assert "31311537537" in d["permissionDecisionReason"], "must name the live run"


def test_an_off_main_dispatch_is_not_the_livelock(monkeypatch):
    """The group is per-ref; a branch dispatch cannot touch main's proof."""
    _runs(monkeypatch, _run_row("in_progress"))
    assert not _denied("gh workflow run ci.yml --ref claude/some-branch")
    assert not _denied("gh workflow run ci.yml --ref refs/heads/feature")


def test_a_workflow_that_is_not_a_main_proof_is_never_probed(monkeypatch):
    """render/daily dispatches are ordinary work and must stay free."""
    _runs(monkeypatch, _run_row("in_progress"))
    assert not _denied("gh workflow run render.yml --ref main")
    assert not _denied("gh workflow run daily.yml --ref main")


def test_flags_before_the_workflow_name_still_resolve(monkeypatch):
    """`--ref main ci.yml` must not read `main` as the workflow."""
    _runs(monkeypatch, _run_row("in_progress"))
    assert _denied("gh workflow run --ref main ci.yml")
    assert _denied("gh workflow run -R owner/repo ci.yml --ref main")
    assert _denied("gh workflow run .github/workflows/ci.yml --ref main")


def test_the_probe_failing_fails_open_and_says_so(monkeypatch):
    """ANTI-WASTE, NOT A SAFETY GATE. A fail-closed deny here would wedge the very
    recovery lever the guard protects — the exact shape of the livelock, one layer
    up. Rate limiting is the likeliest failure, and it is likeliest precisely when
    main is in trouble."""
    monkeypatch.setenv("GH_SHIM_EXIT", "1")
    proc = _raw("gh workflow run ci.yml --ref main")
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == "", "fail-open must ALLOW (stdout stays empty)"
    err = proc.stderr.decode()
    assert "fail-open" in err.lower(), f"the warning must be loud, got: {err!r}"
    assert "ci.yml" in err


def test_unparseable_probe_output_fails_open(monkeypatch):
    monkeypatch.setenv("GH_SHIM_PAYLOAD", "not json at all")
    assert not _denied("gh workflow run ci.yml --ref main")


def test_the_denial_teaches_the_livelock_and_gives_the_watch_command(monkeypatch):
    """A guard that only says no teaches nothing — the next session repeats it."""
    _runs(monkeypatch, _run_row("in_progress", run_id=31309720615))
    d = _run("gh workflow run ci.yml --ref main")
    reason = (d or {}).get("permissionDecisionReason", "")
    assert "cancel" in reason.lower(), "must quote the livelock: a re-dispatch cancels"
    assert "31309720615" in reason, "must name the run to wait on"
    assert "gh run watch 31309720615 --interval 60" in reason, "must give the watch cmd"
    assert "30-34" in reason, "must set the expectation for how long to wait"


def test_the_watch_command_the_denial_recommends_is_itself_allowed(monkeypatch):
    """The remedy must survive the guard's own shape-1 rule, or the deny is a dead end."""
    assert not _denied("gh run watch 31309720615 --interval 60")


def test_prose_about_the_dispatch_is_not_a_dispatch(monkeypatch):
    _runs(monkeypatch, _run_row("in_progress"))
    assert not _denied("echo 'never run gh workflow run ci.yml --ref main while one is live'")
    assert not _denied('git commit -m "guard gh workflow run ci.yml re-dispatches"')


# ─────────────────────────────────────────────────────────────────────────────
# The RETIRED shape 5: CI observation is legal again (operator, 2026-08-12)
# ─────────────────────────────────────────────────────────────────────────────
#
# This guard once carried a fifth shape: once a worker had armed `merge-on-green`
# and written a handoff sentinel, ANY command that read CI state was denied, on
# the theory that the sweeper owned the merge from there.
#
# The operator removed that rule. A session owns its pull request through
# commit -> push -> PR -> CI -> squash-merge -> live verification, so reading check
# state is part of the job, not a violation of it — and in the field the deny
# blocked a session from even DIAGNOSING the red its own pull request was stuck on
# while it sat `merge-blocked`.
#
# Shapes 1-4 are untouched and still decide everything below. They govern HOW a
# session watches CI (one slow watcher, no unthrottled loop, no `--paginate` over
# check-runs, no re-dispatch over a live proof) — never WHETHER it may.

@pytest.mark.parametrize("cmd", [
    # Every one of these was a shape-5 deny. Each is now judged by shapes 1-4
    # alone, and each passes them: a slow watcher, a one-shot read, or a polite loop.
    "gh run watch 31309720615 --interval 60",
    "gh pr checks 4242 --watch",
    "gh pr checks 4242",
    "gh run view 31309720615",
    "gh run view 31309720615 --log-failed",
    'gh api "repos/acme/widgets/commits/$SHA/check-runs?per_page=100"',
    "gh api repos/acme/widgets/actions/runs/31309720615 --jq '.status'",
    "gh api repos/acme/widgets/actions/runs/1/jobs",
    "until [ x = y ]; do gh pr view 4242 --json state; sleep 300; done",
])
def test_ci_observation_is_never_denied_for_owning_an_open_pull_request(cmd):
    """No state outside the command line may make a CI read illegal.

    The session that armed the label is the session that still has to land the
    merge; a guard that hid the check state from it turned an unfinished job into
    a reported-complete one.
    """
    assert not _denied(cmd)


def test_the_quota_shapes_still_decide_the_same_commands():
    """Control for the test above: retiring shape 5 must not have retired shape 1.

    Same verb, same subject, same session — only the interval differs, and that is
    now the ONLY thing that decides.
    """
    assert _denied("gh run watch 31309720615"), "the 3s default is still the trap"
    assert not _denied("gh run watch 31309720615 --interval 60")


def test_no_gh_command_is_denied_merely_because_a_pull_request_is_armed():
    """The words that used to end a worker's life must not appear in any deny.

    A grep-level pin. The retired shape denied with "CI HANDOFF IN EFFECT" and
    told the session to print a terminal marker instead of finishing; it resolved
    that state through a now-deleted contract module loaded by file path. One
    lowercase substring covers the rule, its deny text, its marker, and its
    module, in every casing anyone would reintroduce them in.
    """
    assert "handoff" not in HOOK.read_text(encoding="utf-8").lower()


class _ExplodingSubprocess:
    """Any use at all is the failure — this records nothing, it just refuses."""

    def __init__(self):
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append(args)
        raise AssertionError(f"a command outside shape 4 must spawn no subprocess: {args!r}")


@pytest.mark.parametrize("cmd", [
    "gh pr comment 4242 --body hi",
    "gh pr edit 4242 --add-label merge-on-green",
    "gh issue list",
    "gh api rate_limit --jq '.resources.core.remaining'",
    "gh pr create --title x --body y",
    "gh pr merge 4242 --squash",
    "gh pr view 4242 --json state",
    "gh run rerun --failed 302186",
    "gh run watch 302186 --interval 60",
    "gh pr checks 4242",
])
def test_a_command_outside_shape_four_costs_no_subprocess(monkeypatch, cmd):
    """ORDER IS THE CONTRACT: cheap regex first, subprocesses only after a match.

    Shape 4's probe is one REST call against the pool this hook exists to protect,
    so it may only ever be spent on an exact `gh workflow run <proof>` match.
    Pinned at the seam rather than by inspection.
    """
    exploding = _ExplodingSubprocess()
    monkeypatch.setattr(GUARD, "subprocess", exploding)
    assert GUARD.check(cmd, "/some/checkout") is None
    assert exploding.calls == []


def test_the_probe_gate_is_not_vacuous(monkeypatch):
    """Control for the test above: a real proof dispatch MUST reach the probe, or
    the no-subprocess pin would pass by matching nothing at all."""
    seen = []
    monkeypatch.setattr(GUARD, "live_proof_reason", lambda workflow: seen.append(workflow))
    assert GUARD.check("gh workflow run ci.yml --ref main", "/some/checkout") is None
    assert seen == ["ci.yml"], "the probe runs, and is told which workflow to look at"


def test_prose_about_the_quota_traps_is_not_an_invocation():
    """Writing ABOUT the trap stays legal — the lesson shape 1 learned in production
    the first minute it was live, when it blocked its own commit message."""
    assert not _denied("echo 'do not gh run watch at the default interval'")
    assert not _denied('git commit -m "deny gh pr checks in a tight loop"')


# ─────────────────────────────────────────────────────────────────────────────
# Shape 6 — production lanes a session may not stop
# ─────────────────────────────────────────────────────────────────────────────
#
# Prose forbade this from 2026-08-12 and did not bind: a live fleet session
# force-cancelled the US nightly's recovery dispatches SIX times (receipt: POST
# /actions/runs/31583415065/force-cancel), and stacked on the #5362 workflow-size
# strand the night before, Prophet US served Aug-10 picks for two full sessions.
#
# The 2026-08-14 addition is the WATCHDOG half. daily.yml and the render lanes are
# protected because killing one destroys data; nightly-liveness.yml and
# prophet-rescue.yml are protected because killing one destroys the only thing that
# would have NOTICED. That is the strictly worse outcome: a silenced alarm and a
# healthy night leave the same trace, which is the equivalence the whole outage
# turned on.

KILL_RECEIPT = "31583415065"          # the real run id from the 2026-08-12 receipt


def _lane(monkeypatch, workflow: str) -> None:
    """Make the guard's one `gh api … --jq .path` probe answer for `workflow`."""
    monkeypatch.setenv("GH_SHIM_PAYLOAD", f".github/workflows/{workflow}\n")


@pytest.mark.parametrize("workflow", sorted(GUARD.PROTECTED_LANES))
def test_no_protected_lane_may_be_stopped(monkeypatch, workflow):
    _lane(monkeypatch, workflow)
    assert _denied(f"gh run cancel {KILL_RECEIPT}"), workflow


@pytest.mark.parametrize("workflow", ["nightly-liveness.yml", "prophet-rescue.yml"])
def test_the_prophet_watchdog_lanes_are_protected(monkeypatch, workflow):
    """Named rather than only swept by the parametrize above: removing either entry
    from PROTECTED_LANES must red a test that says WHY it was there."""
    assert workflow in GUARD.PROTECTED_LANES
    _lane(monkeypatch, workflow)
    reason = GUARD.protected_cancel_reason(KILL_RECEIPT)
    assert reason and workflow in reason
    assert _denied(f"gh run cancel {KILL_RECEIPT}")


@pytest.mark.parametrize("cmd", [
    f"gh api -X POST repos/o/r/actions/runs/{KILL_RECEIPT}/cancel",
    f"gh api --method POST /repos/o/r/actions/runs/{KILL_RECEIPT}/force-cancel",
])
def test_both_rest_spellings_are_denied_for_a_watchdog_lane(monkeypatch, cmd):
    """The force-cancel spelling IS the 2026-08-12 receipt, so it is pinned by
    example rather than by inference."""
    _lane(monkeypatch, "prophet-rescue.yml")
    assert _denied(cmd)


def test_an_unprotected_lane_may_still_be_stopped(monkeypatch):
    """Control: without this, every test above could pass by denying everything."""
    _lane(monkeypatch, "ci.yml")
    assert not _denied(f"gh run cancel {KILL_RECEIPT}")


def test_an_unresolvable_run_fails_open(monkeypatch):
    """Fail-open like every other rule in this guard: if the probe cannot say which
    workflow a run belongs to, the guard must not brick the harness."""
    monkeypatch.setenv("GH_SHIM_EXIT", "1")
    assert not _denied(f"gh run cancel {KILL_RECEIPT}")


# ─────────────────────────────────────────────────────────────────────────────
# Shape 7 — re-reading the same status faster than it can change (2026-08-27)
#
# The second time an operator had to say it, and the first time a background
# watcher was ALREADY armed while the session polled anyway. These pin the
# semantics that make the rule safe to enforce: it delays a repeat, it never
# blocks a session, and it never touches a mutation.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def _poll_state(tmp_path, monkeypatch):
    """Isolate the cooldown ledger.

    Via the ENV, not `monkeypatch.setattr`: `_run` executes the hook as a
    SUBPROCESS, so patching the imported module object would leave the real
    shared ledger in play and make these tests order-dependent on any other
    session polling the same PR.
    """
    monkeypatch.setenv("MACRO_GH_POLL_STATE_DIR", str(tmp_path / "cooldown"))
    monkeypatch.setattr(GUARD, "POLL_STATE_DIR", str(tmp_path / "cooldown"))
    return tmp_path


def _nudged(cmd: str) -> str:
    """The additionalContext a repeat read attaches, or "" when silent."""
    d = _run(cmd)
    return (d or {}).get("additionalContext") or ""


def test_first_read_of_a_status_shape_always_passes(_poll_state):
    """The guard governs HOW you watch, never WHETHER: the first look is free."""
    assert not _denied("gh pr checks 6555 --json name,bucket")


def test_immediate_reread_of_the_same_shape_is_flagged_but_allowed(_poll_state):
    """The measured 2026-08-27 burn: one poll per Stop-hook cycle, ~25 in a row,
    against a 30-45 minute run that cannot have changed.

    Flagged, never denied — the CI-observation invariant below is the older and
    stronger rule, so this shape informs the session and lets the call through.
    """
    assert _nudged("gh pr checks 6555 --json name,bucket") == ""
    second = _nudged("gh pr checks 6555 --json name,bucket")
    assert "REDUNDANT POLL" in second
    assert not _denied("gh pr checks 6555 --json name,bucket")


def test_the_nudge_says_it_is_advice_and_names_the_countermeasure(_poll_state):
    """Advice that reads as a block invites evasion, and advice that only scolds
    changes nothing. It must say the call went through, and say what to do."""
    _run("gh pr checks 6555")
    note = _nudged("gh pr checks 6555")
    assert "ADVICE, not a block" in note
    assert "going through" in note
    assert "watcher" in note
    # the specific trap that defeated the prose version
    assert "Stop hook" in note


def test_a_different_run_or_pr_is_a_different_shape(_poll_state):
    """Polling one PR must never blind a session to another one."""
    assert not _denied("gh pr checks 6555")
    assert not _denied("gh pr checks 6554")
    assert not _denied("gh api repos/o/r/actions/runs/33129766342")


def test_the_window_self_clears(_poll_state, monkeypatch):
    """Time-based only: nothing a session does can leave it permanently unable
    to read its own PR."""
    assert not _denied("gh pr checks 6555")
    real = GUARD.time.time
    monkeypatch.setattr(GUARD.time, "time", lambda: real() + GUARD.POLL_COOLDOWN_S + 1)
    assert not _denied("gh pr checks 6555")


@pytest.mark.parametrize("cmd", [
    "gh pr edit 6555 --add-label merge-on-green",
    "gh pr merge 6555 --squash",
    "gh pr comment 6555 --body hi",
    "gh pr create --title x --body y",
])
def test_mutations_are_never_polls(_poll_state, cmd):
    """Repeating a mutation is a different mistake with a different remedy; this
    shape must not silently rate-limit the ship loop's own write path."""
    assert not _denied(cmd)
    assert not _denied(cmd)


def test_unwritable_state_fails_open(_poll_state, monkeypatch):
    """Every rule in this guard fails open. A cooldown ledger that cannot be
    written is not evidence that a poll just happened."""
    monkeypatch.setattr(GUARD, "POLL_STATE_DIR", "/proc/nonexistent/cannot-create")
    assert not _denied("gh pr checks 6555")
    assert not _denied("gh pr checks 6555")


def test_a_command_denied_by_another_shape_does_not_start_the_cooldown(_poll_state):
    """Shape 7 runs LAST. If it recorded first, a denial would start a cooldown
    for a read that never reached GitHub, and the session would then be told to
    wait for a poll it never got to make."""
    hot = "gh run watch 123"                     # shape 1 denies this
    assert _denied(hot)
    # a denied command is not a poll, so an unrelated first read stays silent
    assert _nudged("gh pr checks 6555") == ""


def test_a_heredoc_that_merely_mentions_polling_is_not_a_poll(_poll_state):
    """The trap this file was built around, one shape later: a heredoc body is
    DATA. Shape 1 once blocked its own introducing commit; shape 7 flagged the
    very edit that documents it, because main() passed the RAW command."""
    doc = (
        "python3 - <<'PY'\n"
        "text = 'one `gh pr checks <n>` per Stop-hook cycle while a 30-45 minute run finishes'\n"
        "PY"
    )
    assert _nudged(doc) == ""
    assert _nudged(doc) == ""
