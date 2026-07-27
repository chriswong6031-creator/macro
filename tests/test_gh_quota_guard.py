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

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "gh_quota_guard.py"


def _run(cmd: str, tool: str = "Bash") -> dict | None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}).encode(),
        capture_output=True,
        timeout=10,
    )
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
