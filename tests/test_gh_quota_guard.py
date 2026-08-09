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
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "gh_quota_guard.py"

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


def _raw(cmd: str, tool: str = "Bash") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}).encode(),
        capture_output=True,
        timeout=30,
    )


def _run(cmd: str, tool: str = "Bash") -> dict | None:
    proc = _raw(cmd, tool)
    assert proc.returncode == 0, "the guard must never brick the harness"
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out:
        return None
    return json.loads(out).get("hookSpecificOutput")


def _denied(cmd: str) -> bool:
    d = _run(cmd)
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
