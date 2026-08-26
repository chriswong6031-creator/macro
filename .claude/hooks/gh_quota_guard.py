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
  4. Re-dispatching a main PROOF workflow (ci.yml / fences.yml /
     integration-baseline.yml) while one is already in flight on main
     (2026-08-09). This one is not about request count, it is about the same
     reflex: a pinned session re-firing the documented recovery lever. Until
     that day every main dispatch of ci.yml landed in `ci-refs/heads/main` with
     a flat `cancel-in-progress: true`, so the second dispatch did not queue —
     it KILLED the first. Measured: run 31309720615 was cancelled 44 minutes in
     by dispatch 31311537537, itself cancelled 4 minutes later by 31311693575,
     while 12 merge-blocked + 56 cap-deferred pull requests waited on a proof
     that could therefore never conclude. The workflows are fixed (the flag is
     event-conditional as of the same day), so a race is now merely wasteful
     rather than destructive — but the reflex is what opened the wound, and a
     run already holding a runner is the fastest proof available. Allowed when
     the in-flight run is an orphan (queued > 40 min), and fail-OPEN on any
     probe error: this guard is anti-waste, and a fail-closed deny would wedge
     the very recovery lever it protects.
  6. CANCELLING A PRODUCTION LANE (2026-08-12). Not a quota shape at all — the
     same reflex, one step further. A live fleet session force-cancelled the US
     nightly's recovery dispatches six times (receipt: POST
     /actions/runs/31583415065/force-cancel); stacked on the #5362 workflow-size
     strand the night before, Prophet US served Aug-10 picks for two full
     sessions and the operator found it by looking at the site. A cancel is
     invisible to every staleness instrument we own, because a killed bake and a
     bake that never fired leave the same trace: nothing. CLAUDE.md already
     forbade this in prose ("never cancel or manually re-run an in-progress
     render, engine-render or daily merely to unblock this session"); prose did
     not bind. Denies a cancel aimed at a data-advancing or publishing lane and
     fails OPEN when the run cannot be resolved — an operator can still kill a
     genuinely wedged run, that is just no longer something a session does on
     its own initiative.

A session owns its pull request through to the merge, so it WILL be watching CI.
Shapes 1-4 govern HOW that watching happens, never WHETHER it may: one
slow watcher per endpoint (`--interval 60` or higher), preflight
`gh api rate_limit`, and an empty or 403 response read as "unknown" rather than
as settled. This guard never denies a `gh` call merely because a pull request is
open or armed.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys

MIN_SLEEP = 90       # seconds between gh polls in a loop
MIN_WATCH_INTERVAL = 60
#: A queued run older than this is presumed orphaned (GitHub has scheduled runs that
#: never start — see the "queued run can be ORPHANED" note). Re-dispatching over one
#: is the mercy kill, so the guard must not stand in its way. Well above a run's own
#: 30-34 minute duration, so a healthy in-flight proof never trips it.
ORPHANED_QUEUE_MINUTES = 40
#: One `gh run list` call. Bounded so a hung probe cannot hang the harness.
PROBE_TIMEOUT_S = 20
#: The workflows whose runs on main ARE main's proof (merge_on_green.MAIN_PROOF_WORKFLOWS
#: plus the circuit breaker's baseline). Dispatching any of them over a live one is the
#: shape this guard exists to stop.
PROOF_WORKFLOWS = ("ci.yml", "fences.yml", "integration-baseline.yml")

#: Lanes whose runs a session may NOT cancel (shape 6). These are the lanes that
#: advance data or publish the site: killing one costs a session of ledger the next
#: night cannot re-derive, and the loss is invisible to every staleness instrument
#: because a cancelled run looks exactly like a bake that never fired.
#: The second family (2026-08-14) is the WATCHDOGS over those lanes. They advance
#: no data, so the first rationale does not reach them — but killing one is strictly
#: worse than killing a bake: it removes the only thing that would have noticed. A
#: silenced alarm and a healthy night are the same trace, which is the exact
#: equivalence that let Prophet US serve Aug-10 picks for two sessions.
PROTECTED_LANES = frozenset({
    "daily.yml",            # Build B — the sole authoritative, ledger-advancing bake
    "closing-bell.yml",     # Build A — the provisional close render
    "asia-close.yml",       # the CN/HK bake
    "render.yml",
    "engine-render.yml",
    "weekly.yml",
    "nightly-liveness.yml",  # dead-man switch over daily.yml (detects)
    "prophet-rescue.yml",    # bounded self-heal over daily.yml (responds)
})

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

#: Shape 6. `gh run cancel <id>` plus both REST spellings the fleet has actually
#: used — the force-cancel receipt from 2026-08-12 is the second form.
CANCEL_RE = re.compile(
    CMD_POS + r"gh\s+run\s+cancel\b[^;&|\n]*?(?<![\w-])(?P<id>\d{6,})\b"
)
CANCEL_API_RE = re.compile(r"/actions/runs/(?P<id>\d{6,})/(?:force-)?cancel\b")
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
# `gh workflow run <workflow> [--ref <ref>]` — the main-proof dispatch (shape 4).
WORKFLOW_RUN_RE = re.compile(CMD_POS + r"gh\s+workflow\s+run\b(?P<args>[^;&|\n]*)")
REF_RE = re.compile(r"(?:--ref|(?<!\w)-r)[=\s]+(\S+)")
# gh flags that consume the NEXT token, so it is not mistaken for the workflow name.
VALUE_FLAGS = {"--ref", "-r", "--repo", "-R", "--field", "-f", "--raw-field", "-F",
               "--json", "--jq", "-q", "--template", "-t", "--input"}
MAIN_REFS = {"main", "refs/heads/main", "origin/main"}


def dispatch_target(args: str):
    """(workflow basename, ref or None) for a `gh workflow run` argument string."""
    ref_m = REF_RE.search(args)
    ref = ref_m.group(1).strip("\"'") if ref_m else None
    tokens = args.split()
    skip = False
    workflow = None
    for tok in tokens:
        if skip:
            skip = False
            continue
        if tok.startswith("-"):
            if "=" not in tok and tok in VALUE_FLAGS:
                skip = True
            continue
        workflow = os.path.basename(tok.strip("\"'"))
        break
    return workflow, ref


def warn(msg: str):
    """Loud, but never a deny. Stdout is the harness's decision channel — an ALLOW
    must print nothing there — so the fail-open notice goes to stderr."""
    print(f"GH QUOTA GUARD (fail-open): {msg}", file=sys.stderr, flush=True)


def run_workflow_path(run_id: str):
    """The workflow file a run belongs to, or None when the probe cannot answer.

    ONE REST call, spent only after the command has already matched a cancel of a
    specific run id. None means "unknown" -> allow, never deny.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}",
             "--jq", ".path"],
            capture_output=True, timeout=PROBE_TIMEOUT_S,
        )
    except Exception as exc:
        warn(f"could not resolve run {run_id} ({exc.__class__.__name__})")
        return None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        warn(f"`gh api` failed for run {run_id} (exit {proc.returncode}): {detail}")
        return None
    path = proc.stdout.decode("utf-8", errors="replace").strip()
    return path.rsplit("/", 1)[-1] if path else None


def protected_cancel_reason(run_id: str):
    """Deny a cancel aimed at a production lane. See shape 6 in the docstring."""
    workflow = run_workflow_path(run_id)
    if workflow is None or workflow not in PROTECTED_LANES:
        return None
    return (
        f"PRODUCTION LANE: run {run_id} belongs to `{workflow}`, which this session "
        "may not cancel.\n\n"
        "On 2026-08-12 a live fleet session force-cancelled the US nightly's recovery "
        "dispatches SIX times (receipt: POST /actions/runs/31583415065/force-cancel). "
        "Combined with the #5362 workflow-size strand the night before, Prophet US "
        "shipped Aug-10 picks for two full sessions and the operator found it by "
        "looking at the site. A cancel is invisible to every data-staleness "
        "instrument we own — it just looks like the bake never happened.\n\n"
        "CLAUDE.md already says it: never cancel or re-run an in-progress `render`, "
        "`engine-render` or `daily` merely to unblock this session; a long job inside "
        "its timeout is not evidence that it is wedged. That note did not bind, so "
        "this hook does.\n\n"
        "If the run is genuinely wedged (past its timeout-minutes, or provably "
        "orphaned), that is an OPERATOR call — say so and hand it over. Cancelling a "
        "healthy bake costs a whole session of data that only the next night, or a "
        "force-majeure backfill, can recover."
    )


def main_runs(workflow: str):
    """Newest runs of `workflow` on main, or None when the probe cannot answer.

    ONE REST call. None means "unknown", which the caller turns into an allow —
    never into a deny (see the fail-open note in the module docstring).
    """
    try:
        proc = subprocess.run(
            ["gh", "run", "list", "--workflow", workflow, "--branch", "main",
             "--limit", "20", "--json", "status,createdAt,databaseId,url"],
            capture_output=True, timeout=PROBE_TIMEOUT_S,
        )
    except Exception as exc:                      # gh missing, timeout, anything
        warn(f"could not probe {workflow} runs on main ({exc.__class__.__name__})")
        return None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        warn(f"`gh run list` failed for {workflow} (exit {proc.returncode}): {detail}")
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "[]")
    except Exception:
        warn(f"unparseable `gh run list` output for {workflow}")
        return None
    return data if isinstance(data, list) else None


def age_minutes(stamp):
    try:
        when = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except Exception:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - when).total_seconds() / 60.0


def live_proof_reason(workflow: str):
    """Deny reason when a proof run of `workflow` is already live on main."""
    runs = main_runs(workflow)
    if runs is None:
        return None                               # unknown -> allow
    in_flight = [r for r in runs
                 if isinstance(r, dict) and (r.get("status") or "") != "completed"]
    if not in_flight:
        return None
    newest = max(in_flight, key=lambda r: str(r.get("createdAt") or ""))
    status = newest.get("status") or "?"
    age = age_minutes(newest.get("createdAt"))
    if status == "queued" and age is not None and age > ORPHANED_QUEUE_MINUTES:
        return None                               # orphaned-queue mercy kill
    run_id = newest.get("databaseId") or "<id>"
    url = newest.get("url") or ""
    aged = f"{age:.0f} min" if age is not None else "unknown age"
    return (
        f"MAIN PROOF ALREADY IN FLIGHT: {workflow} run {run_id} is {status} on main "
        f"({aged}). {url}\n\n"
        "Do not re-dispatch it. This is the 2026-08-09 livelock: main-ref dispatches "
        "share one concurrency group, and a re-dispatch USED TO CANCEL the in-flight "
        "proof — run 31309720615 died at 44 minutes to dispatch 31311537537, which "
        "died 4 minutes later to 31311693575, so no proof ever concluded and 12 "
        "merge-blocked + 56 cap-deferred pull requests could not drain. The workflows "
        "now fence dispatches out of the cancel path, so a second dispatch no longer "
        "kills the first — it is simply waste, and the run already holding a runner is "
        "the fastest proof you can get.\n\n"
        f"Watch the one that is running instead:\n"
        f"  gh run watch {run_id} --interval 60\n"
        f"A ci.yml run here takes 30-34 minutes. Re-dispatch only after it CONCLUDES, "
        f"or if it has sat `queued` more than {ORPHANED_QUEUE_MINUTES} minutes (an "
        "orphaned queue slot, which this guard already lets through)."
    )


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


def hot_watch_reason(raw: str):
    """Return the canonical hot ``gh run watch`` denial, if any.

    Kept as one pure helper so another simultaneously configured admission
    hook can avoid creating durable state for a command this guard will deny.
    This is still one decision plane: the quota guard owns the rule and text;
    callers only consult it before reserving their own resource.
    """
    cmd = strip_heredocs(raw)
    match = WATCH_RE.search(cmd)
    if not match:
        return None
    tail = cmd[match.start():]
    interval = INTERVAL_RE.search(tail)
    seconds = int(interval.group(1)) if interval else 3
    if seconds >= MIN_WATCH_INTERVAL:
        return None
    return (
        f"SHARED GITHUB QUOTA: `gh run watch` polls every {seconds}s "
        f"(gh's default is 3s), fetching the run AND its jobs each time. "
        f"REST's 5,000/hr is ONE bucket for every session, the babysitter, "
        f"and ship_loop_guard.py (which fails closed when rate-limited). "
        f"Three 10-minute windows of this emptied it on 2026-07-26.\n\n"
        f"Use --interval {MIN_WATCH_INTERVAL} or higher, or better:\n\n{REMEDY}"
    )


def check(raw: str, cwd=None):
    """Return a deny reason, or None to allow.

    `cwd` is the invoking checkout as the harness reports it. No rule here reads
    it today — every shape is decided from the command string plus, for shape 4,
    one bounded `gh run list` probe — but the parameter is part of the hook's
    call signature and is kept so a future checkout-scoped rule needs no change
    at the `main()` seam.
    """
    cmd = strip_heredocs(raw)

    # 1. gh run watch at a hot interval
    reason = hot_watch_reason(raw)
    if reason:
        return reason

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

    # 4. dispatching a main proof workflow over one that is already in flight.
    # Probed LAST and only on an exact match, so the one REST call this guard
    # spends is never spent on an unrelated command line.
    for m in WORKFLOW_RUN_RE.finditer(cmd):
        workflow, ref = dispatch_target(m.group("args"))
        if workflow not in PROOF_WORKFLOWS:
            continue
        # No --ref means gh targets the default branch, which is main here.
        if ref is not None and ref not in MAIN_REFS:
            continue
        reason = live_proof_reason(workflow)
        if reason:
            return reason

    # 6. cancelling a production lane. Probed LAST and only on an exact run-id
    # match, so the one REST call is never spent on an unrelated command line.
    seen: set[str] = set()
    for m in list(CANCEL_RE.finditer(cmd)) + list(CANCEL_API_RE.finditer(cmd)):
        run_id = m.group("id")
        if run_id in seen:
            continue
        seen.add(run_id)
        reason = protected_cancel_reason(run_id)
        if reason:
            return reason

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
    # The harness names the invoking checkout. `check` does not consult it today,
    # but passing it through keeps this seam stable for a checkout-scoped rule.
    cwd = payload.get("cwd")
    try:
        reason = check(cmd, str(cwd) if cwd else None)
    except Exception:
        allow()          # fail open
    if reason:
        deny(reason)
    allow()


if __name__ == "__main__":
    main()
