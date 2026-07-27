#!/usr/bin/env python3
"""PreToolUse guard: keep one session from eating the shared GitHub REST quota.

WHY THIS EXISTS (2026-07-26, twice in one day, two different sessions).
`gh` authenticates as ONE account token, so REST's 5,000/hr `core` pool is a
single bucket shared by every parallel Claude session, the babysitter lane, and
the hooks themselves. Burning it does not slow one session down, it 403s all of
them for up to an hour.

The sharpest bite is self-inflicted: `.claude/hooks/ship_loop_guard.py` spends up
to four REST calls per Stop evaluation and FAILS CLOSED on rate limiting. So
polling hard to watch CI blocks the very Stop the watching was meant to reach.

A memory note (`ci-poll-quota-and-false-settle`) already described all of this,
and a session walked into it an hour after another session wrote it down. Notes
do not bind; a hook does. This denies only the three shapes that provably burned
the pool, and fails OPEN on everything else — a guard that bricks the harness is
worse than a missed warning.

  1. `gh run watch` at its DEFAULT 3-second interval. Ten minutes of that is
     ~200 polls, each fetching the run AND its jobs (this repo runs ~130 checks
     per PR). Three such windows exhausted 5,000 calls. Allowed with an explicit
     `--interval`/-i of >= 60.
  2. A `gh` call in a poll loop sleeping under 90s. Two watchers on one endpoint
     at 45s took 4,488 -> 0 in under an hour.
  3. `--paginate` against check-runs/jobs. ~130 checks is several pages per poll,
     and one page already answers "is it still running".
"""
import json
import re
import sys

MIN_SLEEP = 90       # seconds between gh polls in a loop
MIN_WATCH_INTERVAL = 60

REMEDY = (
    "Poll on a slow cadence and check the pool first:\n"
    "  REM=$(gh api rate_limit --jq '.resources.core.remaining')\n"
    "  [ \"$REM\" -lt 60 ] && { sleep 150; continue; }   # back off, do NOT treat as settled\n"
    "  S=$(gh api \"repos/OWNER/REPO/actions/runs/$RUN\" --jq '\"\\(.status)/\\(.conclusion // \"-\")\"')\n"
    "  [ -z \"$S\" ] && { sleep 150; continue; }          # empty != finished\n"
    "  sleep 150\n"
    "One watcher per endpoint. An empty/403 response is NOT a green result."
)

# Heredoc bodies are DATA, not commands. Caught in production the first minute
# this hook was live: it blocked the very commit that introduced it, because the
# commit message documents `gh run watch`. A guard that forbids writing ABOUT the
# trap is worse than useless — it stops the fix and the postmortem.
HEREDOC_RE = re.compile(
    r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\s*\2\s*$",
    re.S | re.M,
)


def strip_heredocs(cmd: str) -> str:
    """Remove heredoc bodies so prose about gh is not read as gh invocations."""
    prev = None
    out = cmd
    while prev != out:                     # nested / successive heredocs
        prev = out
        out = HEREDOC_RE.sub("<<HEREDOC", out)
    return out


# A gh call only counts at a COMMAND position: start, or after a separator
# (; && || | & newline) or a loop keyword. Keeps "# never use gh run watch" and
# `-m "...gh run watch..."` prose from reading as an invocation.
CMD_POS = r"(?:^|[;&|\n(]|\b(?:do|then|else)\s)\s*"
# `gh run watch` / `gh run view --watch`
WATCH_RE = re.compile(CMD_POS + r"gh\s+run\s+(?:watch\b|view\b[^|;&\n]*--watch\b)")
INTERVAL_RE = re.compile(r"(?:--interval|(?<!\w)-i)[=\s]+(\d+)")
# any gh subcommand that hits the API (gh auth/help/version are free)
GH_API_RE = re.compile(CMD_POS + r"gh\s+(?:api|run|pr|workflow|search|repo|issue|release)\b")
SLEEP_RE = re.compile(r"\bsleep\s+(\d+)")
# A shell loop BODY, i.e. the span between `do` and `done`. Co-presence of a
# loop keyword and a gh call is NOT enough: the second production false positive
# was `python3 -c "for m in ...: print(...)"` in the same command line as an
# unrelated `gh api rate_limit`. A Python `for` has no `do`/`done`, so requiring
# the real construct — and requiring the gh call to sit INSIDE it — distinguishes
# "polling in a loop" from "a loop and a gh call happen to share a line".
DO_DONE_RE = re.compile(r"(?:^|[;&|\n)])\s*do\b(.*?)\bdone\b", re.S)


def loop_bodies(cmd: str) -> list[str]:
    return [m.group(1) for m in DO_DONE_RE.finditer(cmd)]
PAGINATE_RE = re.compile(CMD_POS + r"gh\s+api\b[^|;&]*--paginate\b[^|;&]*"
                         r"(?:check-runs|/jobs|check_runs)")
# same, other argument order
PAGINATE_RE2 = re.compile(CMD_POS + r"gh\s+api\b[^|;&]*(?:check-runs|/jobs|check_runs)"
                          r"[^|;&]*--paginate\b")


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def check(raw: str):
    """Return a deny reason, or None to allow."""
    cmd = strip_heredocs(raw)
    # 1. gh run watch at a hot interval
    m = WATCH_RE.search(cmd)
    if m:
        tail = cmd[m.start():]
        iv = INTERVAL_RE.search(tail)
        secs = int(iv.group(1)) if iv else 3      # gh's documented default
        if secs < MIN_WATCH_INTERVAL:
            return (
                f"SHARED GITHUB QUOTA: `gh run watch` polls every {secs}s "
                f"(gh's default is 3s), fetching the run AND its jobs each time. "
                f"REST's 5,000/hr is ONE bucket for every session, the babysitter, "
                f"and ship_loop_guard.py (which fails closed when rate-limited). "
                f"Three 10-minute windows of this emptied it on 2026-07-26.\n\n"
                f"Use --interval {MIN_WATCH_INTERVAL} or higher, or better:\n\n{REMEDY}"
            )

    # 2. gh inside a tight poll loop — the gh call must be INSIDE the loop body,
    # not merely somewhere in the same command line.
    polling = [b for b in loop_bodies(cmd) if GH_API_RE.search(b)]
    if polling:
        body = "\n".join(polling)
        sleeps = [int(s) for s in SLEEP_RE.findall(body)]
        if sleeps and min(sleeps) < MIN_SLEEP:
            return (
                f"SHARED GITHUB QUOTA: gh poll loop sleeping {min(sleeps)}s "
                f"(floor is {MIN_SLEEP}s). REST's 5,000/hr is shared across every "
                f"session and the hooks; two watchers on one endpoint at 45s went "
                f"4,488 -> 0 in under an hour, 403ing everyone.\n\n{REMEDY}"
            )
        if not sleeps:
            return (
                "SHARED GITHUB QUOTA: gh call in a loop with no sleep — that is an "
                f"unthrottled hammer on a pool shared with every other session.\n\n{REMEDY}"
            )

    # 3. --paginate over check-runs/jobs
    if PAGINATE_RE.search(cmd) or PAGINATE_RE2.search(cmd):
        return (
            "SHARED GITHUB QUOTA: `--paginate` over check-runs/jobs. This repo runs "
            "~130 checks per PR, so each poll spends several requests where one page "
            "already answers 'is it still running'. Drop --paginate, or ask the run "
            "endpoint for a single status.\n\n" + REMEDY
        )

    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    if (payload.get("tool_name") or "") != "Bash":
        allow()
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        allow()
    cmd = str(ti.get("command") or "")
    if "gh " not in cmd:
        allow()
    try:
        reason = check(cmd)
    except Exception:
        allow()          # fail open
    if reason:
        deny(reason)
    allow()


if __name__ == "__main__":
    main()
