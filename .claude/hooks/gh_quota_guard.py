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
  5. ANY CI observation once the worker has HANDED CI OFF (Wave A). Shapes 1-3
     throttle babysitting; this one ends it. A worker that pushed an exact head,
     armed `merge-on-green`, and wrote a handoff sentinel is TERMINAL — the
     sweeper owns the merge and a controller event owns the resume. Every poll
     after that point is a worker spending shared quota to learn a fact it is no
     longer allowed to act on, and the model burn of the wait is strictly larger
     than the burn of a fresh continuation session (CLAUDE.md: Fable burn is
     CONTEXT x TURNS). The sentinel is keyed on (repo, branch, head), so a NEW
     commit invalidates it automatically and babysitting becomes legal again the
     moment the worker has un-handed-off work. Fails OPEN in every direction:
     unresolvable git, unloadable contract, unreadable sentinel -> allow.
"""
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

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


# ── Shape 5: CI observation after a terminal handoff ────────────────────────
#
# The CHEAP half of the gate. Nothing below this line spends a subprocess until
# one of these matches: a command that is not CI observation must cost exactly
# the regex scan it would have cost before this rule existed.
#
# `gh pr checks` is listed WITHOUT --watch on purpose. Its only use is reading a
# head's check state, which is precisely the fact a handed-off worker is no
# longer allowed to act on; the `--watch` variant is merely the loud version.
OBSERVE_RES = (
    re.compile(CMD_POS + r"gh\s+run\s+(?:watch|view)\b"),
    re.compile(CMD_POS + r"gh\s+pr\s+checks\b"),
    re.compile(
        CMD_POS + r"gh\s+api\b[^|;&\n]*(?:check-runs|check_runs|/jobs|actions/runs)"
    ),
)
#: The pure handoff contract. Loaded BY FILE PATH — this guard must not acquire
#: the application import graph, and the contract imports only the stdlib so it
#: never needs to.
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci_handoff_contract.py"
#: One-slot cache for the loaded contract (a failed load caches None too).
CONTRACT_CACHE = []
#: Local git only — no network. Bounded so a wedged git cannot hang the harness.
GIT_TIMEOUT_S = 10
#: The two sentences a handed-off worker must read, verbatim. The controller's
#: contract with the worker is that these words mean STOP, so they are pinned by
#: test rather than paraphrased per call site.
HANDOFF_TERMINAL_TEXT = (
    "CI ownership was handed to merge-on-green at {head}. This worker is terminal.\n"
    "Start a fresh repair/continuation session only after the controller emits an event."
)


def observes_ci(cmd: str) -> bool:
    """Whether `cmd` reads CI state — the cheap regex gate for shape 5.

    Two shapes: a direct observation command, or a shell loop with any gh API call
    inside it. The loop arm catches the wrapper form (`until ...; do gh pr view
    --json state; sleep 300; done`), which is babysitting even when the inner
    command would be innocent once.
    """
    if any(rx.search(cmd) for rx in OBSERVE_RES):
        return True
    return any(GH_API_RE.search(body) for body in loop_bodies(cmd))


def ci_handoff_contract():
    """`scripts/ci_handoff_contract.py` loaded by path, or None. FAILS OPEN.

    Registered in `sys.modules` under a private name before `exec_module` because
    the contract's `HandoffVerdict` is a `@dataclass` under
    `from __future__ import annotations`: class creation resolves its annotations
    via `dataclasses._is_type`, which dereferences
    `sys.modules.get(cls.__module__)` and dies on an unregistered module. Any
    `sys.path` mutation is rolled back; a failed load leaves nothing behind.

    The name is per-HOOK. `ship_loop_guard.py` loads the same file, and two hooks
    sharing one `sys.modules` key evict each other whenever both run in one
    process — an evicted module with no remaining reference has its globals set to
    None, which rots the other hook's handle mid-call. Cached for the same reason
    plus the obvious one: a re-exec per call would be pure waste.
    """
    if CONTRACT_CACHE:
        return CONTRACT_CACHE[0]
    name = "_mm_ci_handoff_contract_gh_quota_guard"
    module = None
    saved_path = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location(name, CONTRACT_PATH)
        if spec is not None and spec.loader is not None:
            candidate = importlib.util.module_from_spec(spec)
            sys.modules[name] = candidate
            try:
                spec.loader.exec_module(candidate)
            except BaseException:
                sys.modules.pop(name, None)
                raise
            module = candidate
    except Exception as exc:
        warn(f"could not load the CI handoff contract ({exc.__class__.__name__})")
        module = None
    finally:
        sys.path[:] = saved_path
    CONTRACT_CACHE.append(module)
    return module


def git_out(root, *args: str) -> str:
    """One local git read, or "" — never raises, never touches the network."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, timeout=GIT_TIMEOUT_S
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip()


def handoff_sentinel(cwd=None):
    """The ACTIVE handoff sentinel for the checkout at `cwd`, or None.

    "Active" is the contract's word and it includes the head: `active_sentinel`
    returns None for a sentinel written against an OLDER head, so a worker that
    has committed since handing off is free to watch CI again — it has work the
    sweeper was never given.

    Costs three local git reads and one small file read, all of them fail-open.
    Only ever called after `observes_ci` has already matched.
    """
    contract = ci_handoff_contract()
    if contract is None:
        return None
    try:
        root = Path(str(cwd) if cwd else os.getcwd())
        if not root.is_dir():
            return None
        repo = contract.normalize_repo(git_out(root, "config", "--get", "remote.origin.url"))
        branch = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
        head = git_out(root, "rev-parse", "HEAD")
        if not repo or not branch or not head:
            return None
        return contract.active_sentinel(repo, branch, head)
    except Exception as exc:
        warn(f"could not resolve the handoff sentinel ({exc.__class__.__name__})")
        return None


def handoff_deny_reason(sentinel) -> str:
    """Deny reason for observing CI after the handoff. Names the head, always."""
    head = str(sentinel.get("head_sha") or "")
    number = sentinel.get("pr_number")
    pr = f"#{number}" if number else "the armed pull request"
    return (
        "CI HANDOFF IN EFFECT: this command observes CI, and CI is no longer this "
        "worker's to observe.\n\n"
        + HANDOFF_TERMINAL_TEXT.format(head=head)
        + "\n\n"
        f"{pr} is armed with `merge-on-green`. The sweeper merges it once every check "
        "CONCLUDES clean and labels it `merge-blocked` with an explanatory comment if "
        "one is genuinely red — either way a controller event, not a poll, is what "
        "resumes the work. Polling from here spends the shared 5,000/hr REST pool (one "
        "bucket for every session and for ship_loop_guard.py, which fails closed when "
        "rate-limited) to learn a fact this worker may not act on, and it holds a long "
        "context open across the 30-34 minutes a ci.yml run takes — the most expensive "
        "shape there is.\n\n"
        "Print your terminal `CI_HANDOFF=` marker and stop. If you have since made NEW "
        "commits, push them: the sentinel is keyed to the handed-off head, so a moved "
        "HEAD releases this guard on its own."
    )


def warn(msg: str):
    """Loud, but never a deny. Stdout is the harness's decision channel — an ALLOW
    must print nothing there — so the fail-open notice goes to stderr."""
    print(f"GH QUOTA GUARD (fail-open): {msg}", file=sys.stderr, flush=True)


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


def check(raw: str, cwd=None):
    """Return a deny reason, or None to allow."""
    cmd = strip_heredocs(raw)

    # 5. CI observation after a terminal handoff. FIRST, because "you are done" is
    # a better answer than "poll slower" — but strictly regex-gated: `observes_ci`
    # is pure string work, and only a command that already IS CI babysitting may
    # spend the local git reads behind `handoff_sentinel`. A command this guard has
    # no business in must cost nothing.
    if observes_ci(cmd):
        sentinel = handoff_sentinel(cwd)
        if sentinel:
            return handoff_deny_reason(sentinel)

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
    # The harness names the invoking checkout; `check` falls back to this process's
    # cwd, which the harness sets to the same place. Either way the sentinel is
    # keyed on the REMOTE repo and branch, so a sibling worktree of the same branch
    # resolves the same handoff.
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
