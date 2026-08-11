#!/usr/bin/env python3
"""The universal, agent-agnostic terminal CI handoff (`mastermind.ci_handoff.v1`).

WHY THIS EXISTS (operator directive, Wave A).
"System done" and "worker done" are different states. A worker that has pushed an
exact PR head and armed `merge-on-green` has finished its job; the sweeper owns
the merge from there. Before this CLI the release rule was reachable from exactly
one place — `_handoff_verdict` inside `.claude/hooks/ship_loop_guard.py` — so it
was a CLAUDE-shaped rule. Codex, a shell script, a workflow step, or a future
orchestrator had no way to ask the same question and get the same answer, and a
worker that guesses wrong either sits on CI for an hour or orphans its work on a
head the sweeper will never merge.

WHAT IT IS. A worker runs this ONCE, after opening and arming its pull request.
It takes ONE finite snapshot of the head's check runs, decides armed / red /
unproven with `scripts/ci_handoff_contract.py` (the same classifier the Stop hook
holds), records a PRIVATE receipt, writes a local sentinel, prints ONE parseable
terminal marker, and exits.

WHAT IT IS NOT. There is no watch mode, no poll, no retry loop, no wait — not
anywhere in this file. Waiting is what the handoff EXISTS to delete: the
`merge-on-green` sweeper already re-derives everything from GitHub's live state
every ten minutes, and a worker re-asking the same question burns the shared
5,000/hr REST bucket that `ship_loop_guard.py` fails CLOSED without (see
CLAUDE.md, "GitHub quota is ONE shared bucket"). One snapshot, one verdict, out.

PUBLIC-REPO SAFETY. Macro is world-readable forever. The receipt this builds is
PRIVATE: it carries continuation routing and a payload reference. It is published
only to a private sink (control plane, or a private host-state file) and the
sentinel lives OUTSIDE the checkout, under `~/.mastermind/ci_handoffs`. The only
thing that reaches a shareable surface is `contract.terminal_marker`, built from
the field allowlist in `contract.PUBLIC_RECEIPT_FIELDS` and re-proved by
`contract.assert_public_safe`.

BASE SHA. Taken from the pull request's `baseRefOid`, which arrives in the SAME
`gh pr list`/`gh pr view` call that resolves the pull request — zero extra API
calls. When that field is absent (an older `gh`, or a stubbed transport) it falls
back to the local remote-tracking ref `git rev-parse origin/<base_ref>`, and
finally to "" rather than guessing.

USAGE
    python3 scripts/ci_handoff.py                       # after `gh pr edit N --add-label merge-on-green`
    python3 scripts/ci_handoff.py --continuation-id abc --payload-ref private://…
    python3 scripts/ci_handoff.py --pr 5361 --resume-on live --json

EXIT CODES
    0  handoff accepted — the sweeper owns the merge; the worker is done.
    2  the head carries concluded RED checks (named in the message).
    3  the head is UNPROVEN — nothing considered, or everything finished proving
       nothing. An absence of red is not a pass (#4779); releasing here orphans
       the work because the sweeper will never merge it either.
    4  this checkout is not in a handoff-able state: session dirt, an unpushed
       branch, or a pull request head that is not the local HEAD.
    5  no pull request to hand off to: none open for the branch, or it is closed,
       draft, based off something other than `main`, or not armed with
       `merge-on-green`.
    6  a continuation was requested but the private sink could not record it.
    7  infrastructure: `gh`/git/network/rate-limit failure, or an origin remote
       this cannot resolve to `owner/name`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts import ci_handoff_contract as contract  # noqa: E402

EXIT_OK = 0
EXIT_RED = 2
EXIT_UNPROVEN = 3
EXIT_NOT_HANDOFFABLE = 4
EXIT_NOT_ARMED = 5
EXIT_SINK_FAILED = 6
EXIT_INFRA = 7

#: The base branch a handoff may target. The sweeper merges into main and nowhere
#: else, so a pull request based anywhere else has no merge owner at all.
REQUIRED_BASE_REF = "main"

#: Pagination bound for the ONE check-run snapshot, mirroring `_head_check_runs`
#: in `.claude/hooks/ship_loop_guard.py`. PR #3629's head carried 101 check runs,
#: so a single `per_page=100` call truncated and a red beyond the first page was
#: invisible — the gate failed OPEN, the one direction it may never fail. The
#: 5-page cap bounds a pathological head's share of the shared API budget.
CHECK_RUN_PAGE_SIZE = 100
MAX_CHECK_RUN_PAGES = 5

#: Exactly the fields the pull-request query asks for. `baseRefOid` rides along so
#: the receipt's base sha costs no extra call (see the module docstring).
PR_JSON_FIELDS = "number,headRefOid,baseRefOid,baseRefName,isDraft,state,labels,url"

#: Roots holding OTHER agent sessions' checkouts, copied from
#: `.claude/hooks/ship_loop_guard.py`. A session blocked on them has no move that
#: helps: it can neither commit another session's checkout nor delete one without
#: destroying live work. Closed and hardcoded on purpose — this is a hole in the
#: dirty gate, so it has to be reviewable in the diff, and an env-driven lever
#: that could widen it to `/` would turn the gate off.
AGENT_WORKTREE_ROOTS = (
    ".claude/worktrees/",
    ".claire/worktrees/",
    ".codex-worktrees/",
)

#: Where a private Mastermind control plane may be rooted, in resolution order.
CONTROL_PLANE_ROOT_ENVS = ("MASTERMIND_CONTROL_PLANE_ROOT", "MASTERMIND_ROOT")
#: The primitive this reuses. Macro is public and must NEVER hard-depend on it,
#: so it is loaded BY FILE PATH and only when it is actually there.
CONTROL_PLANE_MODULE_REL = Path("control_plane") / "run_events.py"

SINK_CHOICES = ("auto", "control-plane", "local", "none")


class HandoffError(Exception):
    """A terminal refusal: an exit code, an annotation slug, and a human reason."""

    def __init__(self, code: int, slug: str, message: str) -> None:
        super().__init__(message)
        self.code = int(code)
        self.slug = str(slug)
        self.message = str(message)


def _fail(code: int, slug: str, message: str) -> HandoffError:
    return HandoffError(code, slug, message)


def _annotate_error(slug: str, message: str) -> None:
    """One GitHub annotation, at the START of its line, never through a logger.

    House law (CLAUDE.md, CI-guarded by `tests/test_gh_annotation_line_start.py`):
    every builder here logs with a prefixing format, so `log.error("::error …")`
    emits `ERROR ::error …` and GitHub silently drops it — the call reviews as an
    alarm, runs clean, and produces nothing. `flush=True` is load-bearing because
    stdout is block-buffered when piped in CI.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title={slug}::{message}", flush=True)
    else:
        print(f"ci_handoff: {message}", file=sys.stderr, flush=True)


def _annotate_warning(slug: str, message: str) -> None:
    """The fail-soft sibling of `_annotate_error`; same line-start law."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title={slug}::{message}", flush=True)
    else:
        print(f"ci_handoff: {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
def _git_run(root: Path | str, args: Sequence[str], timeout: int) -> str:
    try:
        proc = subprocess.run(
            ("git", *args),
            cwd=str(root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - git is always present here
        raise _fail(EXIT_INFRA, "git-missing", f"git is not on PATH: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise _fail(
            EXIT_INFRA, "git-timeout", f"git {' '.join(args)} timed out after {timeout}s"
        ) from exc
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise _fail(
            EXIT_INFRA, "git-failed", f"git {' '.join(args)} failed: {detail[:400]}"
        )
    return proc.stdout


def _git(root: Path | str, *args: str, timeout: int = 60) -> str:
    return _git_run(root, args, timeout).strip()


def _git_raw(root: Path | str, *args: str, timeout: int = 120) -> str:
    """git output with its leading columns intact — porcelain's status field."""
    return _git_run(root, args, timeout)


def _is_agent_worktree_path(path: str, status: str) -> bool:
    """Whether this porcelain entry belongs to another agent session's checkout.

    Fail-CLOSED on two axes, exactly as `ship_loop_guard._is_agent_worktree_path`
    does. Only UNTRACKED entries qualify — these roots are ignored by
    construction, so anything git TRACKS under one is real repository content and
    keeps gating normally. And the match is anchored at the repository root
    (porcelain paths are root-relative, with no leading `./`), so a nested
    `docs/.codex-worktrees/` deeper in the tree is not excused by a root of the
    same name.
    """
    if status.strip() != "??":
        return False
    return any(path.startswith(root) for root in AGENT_WORKTREE_ROOTS)


def _dirty_entries(root: Path) -> list[str]:
    """Uncommitted entries this checkout owns, other fleets' worktrees excluded."""
    output = _git_raw(root, "status", "--porcelain=v1", "--untracked-files=all")
    entries: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status, display_path = line[:2], line[3:]
        # For rename records the destination is the content-bearing path.
        path = display_path.rsplit(" -> ", 1)[-1].strip('"')
        if _is_agent_worktree_path(path, status):
            continue
        entries.append(f"{status} {path}")
    return entries


def _remote_branch_tip(root: Path, branch: str) -> str:
    """The remote's own tip for `branch`, or "" when the branch is not pushed.

    `git ls-remote` asks the REMOTE, not the local remote-tracking ref: a stale
    `origin/<branch>` would report a push that never happened, and this gate has
    to fail closed.
    """
    output = _git(root, "ls-remote", "origin", f"refs/heads/{branch}", timeout=120)
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == f"refs/heads/{branch}":
            return parts[0].strip()
    return ""


# ---------------------------------------------------------------------------
# gh — THE single seam that shells out. Tests monkeypatch exactly this function.
# ---------------------------------------------------------------------------
def _gh_json(args: Sequence[str], *, timeout: int = 120) -> Any:
    """Run `gh <args>` and parse its JSON stdout.

    Every GitHub read in this module goes through here and nowhere else, so a
    test can drive the whole CLI by replacing one function, and a reader can
    count the network calls by counting the callers. Any failure — a missing
    `gh`, a non-zero exit, a rate-limit refusal, unparseable output — is
    infrastructure (exit 7), never a verdict about the pull request. An empty or
    403 response is NOT a green result.
    """
    argv = ["gh", *[str(a) for a in args]]
    try:
        proc = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise _fail(
            EXIT_INFRA,
            "gh-missing",
            "the GitHub CLI (`gh`) is not on PATH, so the head's checks cannot be read",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise _fail(
            EXIT_INFRA, "gh-timeout", f"`{' '.join(argv)}` timed out after {timeout}s"
        ) from exc
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise _fail(
            EXIT_INFRA, "gh-failed", f"`{' '.join(argv)}` failed: {detail[:400]}"
        )
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise _fail(
            EXIT_INFRA, "gh-bad-json", f"`{' '.join(argv)}` returned unparseable JSON"
        ) from exc


def _head_check_runs(repo: str, head_sha: str) -> list[dict[str, Any]]:
    """ONE finite snapshot of every check run on `head_sha`.

    Bounded pagination, mirroring `_head_check_runs` in `ship_loop_guard.py`: stop
    on a short page or once `total_count` is reached, and never exceed
    `MAX_CHECK_RUN_PAGES`. A full page with no `total_count` keeps paging rather
    than guessing the tail away.
    """
    runs: list[dict[str, Any]] = []
    for page in range(1, MAX_CHECK_RUN_PAGES + 1):
        endpoint = (
            f"repos/{repo}/commits/{head_sha}/check-runs"
            f"?per_page={CHECK_RUN_PAGE_SIZE}&page={page}"
        )
        payload = _gh_json(["api", endpoint])
        if not isinstance(payload, Mapping):
            raise _fail(
                EXIT_INFRA,
                "check-runs-unreadable",
                f"the check-runs listing for {head_sha[:12]} was not an object",
            )
        batch = list(payload.get("check_runs") or [])
        runs.extend(run for run in batch if isinstance(run, Mapping))
        try:
            total = int(payload.get("total_count") or 0)
        except (TypeError, ValueError):
            total = 0
        if len(batch) < CHECK_RUN_PAGE_SIZE or (total and len(runs) >= total):
            break
    return runs


def _resolve_pull(branch: str, pr_number: int | None) -> dict[str, Any]:
    """The pull request being handed off, from `--pr` or from the branch."""
    if pr_number is not None:
        pull = _gh_json(["pr", "view", str(pr_number), "--json", PR_JSON_FIELDS])
        if not isinstance(pull, Mapping):
            raise _fail(
                EXIT_NOT_ARMED,
                "pull-request-unreadable",
                f"pull request #{pr_number} could not be read.",
            )
        return dict(pull)

    listed = _gh_json(
        ["pr", "list", "--head", branch, "--state", "open", "--json", PR_JSON_FIELDS]
    )
    pulls = [dict(item) for item in (listed or []) if isinstance(item, Mapping)]
    if not pulls:
        raise _fail(
            EXIT_NOT_ARMED,
            "no-open-pull-request",
            f"no OPEN pull request has `{branch}` as its head branch, so there is "
            "nothing to hand off. Open one, arm it with "
            f"`gh pr edit <n> --add-label {contract.MERGE_ON_GREEN_LABEL}`, then re-run.",
        )
    return pulls[0]


# ---------------------------------------------------------------------------
# sinks (§5.6)
# ---------------------------------------------------------------------------
class HandoffSink(Protocol):
    """Where a private receipt is recorded so a controller can resume the work."""

    def publish(self, receipt: Mapping[str, object]) -> str: ...


def _receipt_id_of(receipt: Mapping[str, object]) -> str:
    handoff_id = str(receipt.get("handoff_id") or "")
    if not handoff_id:
        raise ValueError("receipt carries no handoff_id, so it cannot be published")
    return handoff_id


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON at `path` atomically — never a half file another reader can see."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


class NullSink:
    """Records nothing. Used ONLY when no continuation was requested.

    A worker with no continuation has nothing for a controller to resume, so
    there is no record to keep and therefore no failure mode to inherit.
    """

    name = "none"

    def publish(self, receipt: Mapping[str, object]) -> str:
        _receipt_id_of(receipt)
        return ""


class LocalPrivateSink:
    """Development fallback: the receipt as a file under the PRIVATE state root.

    `contract.sentinel_root()` is `~/.mastermind/ci_handoffs` (overridable with
    MASTERMIND_CI_HANDOFF_DIR) — deliberately OUTSIDE the repository tree. That
    placement is load-bearing, not tidiness: a receipt written inside the checkout
    shows up in `git status`, gates the ship loop, and eventually gets committed
    to a PUBLIC repository along with whatever continuation context it carries.

    Idempotent by `handoff_id`: re-publishing the same receipt is a no-op that
    returns the same ref.
    """

    name = "local"

    def __init__(self, state_root: str | os.PathLike[str] | None = None) -> None:
        self._state_root = state_root

    def _path(self, handoff_id: str) -> Path:
        return contract.sentinel_root(self._state_root) / "receipts" / f"{handoff_id}.json"

    def publish(self, receipt: Mapping[str, object]) -> str:
        handoff_id = _receipt_id_of(receipt)
        ref = f"private://local/{handoff_id}"
        path = self._path(handoff_id)
        if path.exists():
            return ref
        _atomic_write_json(path, dict(receipt))
        return ref


class ControlPlaneSink:
    """The private Mastermind control plane's existing `run_events.append`.

    Loaded BY FILE PATH (`importlib.util.spec_from_file_location`), never through
    `sys.path` or an import statement: Macro is public and must never acquire a
    hard dependency on the private repository. If the file is not there, this sink
    does not exist — it is not an error, it is a different deployment.

    `run_events.append` has NO idempotency of its own, so this sink keeps a
    key-pointer file per `handoff_id` under the private state root and skips the
    append when that id was already published. The pointer is written only AFTER
    a successful append, so a failed publish stays retryable.
    """

    name = "control-plane"

    def __init__(
        self,
        module_path: Path,
        *,
        control_plane_root: Path | None = None,
        state_root: str | os.PathLike[str] | None = None,
    ) -> None:
        self._module_path = Path(module_path)
        self._control_plane_root = control_plane_root
        self._state_root = state_root

    def _pointer(self, handoff_id: str) -> Path:
        return (
            contract.sentinel_root(self._state_root)
            / "published"
            / "control-plane"
            / f"{handoff_id}.json"
        )

    def _load(self) -> Any:
        spec = importlib.util.spec_from_file_location(
            "mastermind_control_plane_run_events", self._module_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load control plane primitive at {self._module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def publish(self, receipt: Mapping[str, object]) -> str:
        handoff_id = _receipt_id_of(receipt)
        ref = f"private://control-plane/run_events/{handoff_id}"
        pointer = self._pointer(handoff_id)
        if pointer.exists():
            return ref

        module = self._load()
        append = getattr(module, "append", None)
        if not callable(append):
            raise RuntimeError(
                f"{self._module_path} exposes no callable `append(event, *, root=None)`"
            )
        event = {
            "schema": contract.SCHEMA,
            "kind": "CI_HANDOFF_ACCEPTED",
            "idempotency_key": handoff_id,
            "receipt": dict(receipt),
        }
        try:
            result = append(event, root=self._control_plane_root)
        except TypeError:
            # A primitive whose signature predates the keyword still gets the event.
            result = append(event)
        _atomic_write_json(
            pointer,
            {
                "handoff_id": handoff_id,
                "ref": ref,
                "event_ref": None if result is None else str(result),
                "published_at": _utc_now(),
            },
        )
        return ref


def control_plane_module_path() -> Path | None:
    """The private control-plane primitive, when this host actually has one."""
    for env in CONTROL_PLANE_ROOT_ENVS:
        raw = os.environ.get(env, "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser() / CONTROL_PLANE_MODULE_REL
        if candidate.is_file():
            return candidate
    return None


def resolve_sink(
    choice: str,
    *,
    continuation_requested: bool,
    state_root: str | os.PathLike[str] | None = None,
) -> HandoffSink:
    """The sink for `--sink <choice>`.

    `auto` with no continuation is `NullSink`: there is nothing for a controller
    to resume, so writing a record would only create a failure mode. `auto` with a
    continuation prefers the private control plane and falls back to the local
    private file when this host has no control plane.
    """
    if choice == "none":
        return NullSink()
    if choice == "local":
        return LocalPrivateSink(state_root)
    if choice == "control-plane":
        module_path = control_plane_module_path()
        if module_path is None:
            raise RuntimeError(
                "no private control plane on this host: set "
                f"{CONTROL_PLANE_ROOT_ENVS[0]} (or {CONTROL_PLANE_ROOT_ENVS[1]}) to a "
                f"root containing {CONTROL_PLANE_MODULE_REL.as_posix()}"
            )
        return ControlPlaneSink(
            module_path,
            control_plane_root=module_path.parent.parent,
            state_root=state_root,
        )
    if not continuation_requested:
        return NullSink()
    module_path = control_plane_module_path()
    if module_path is not None:
        return ControlPlaneSink(
            module_path,
            control_plane_root=module_path.parent.parent,
            state_root=state_root,
        )
    return LocalPrivateSink(state_root)


def _publish(receipt: Mapping[str, Any], choice: str, continuation_requested: bool) -> str:
    """Publish through the resolved sink. Only a REQUESTED continuation can fail."""
    try:
        sink = resolve_sink(choice, continuation_requested=continuation_requested)
        return sink.publish(receipt)
    except Exception as exc:  # noqa: BLE001 - the sink boundary is deliberately wide
        if continuation_requested:
            raise _fail(
                EXIT_SINK_FAILED,
                "handoff-sink-failed",
                "a continuation was requested but the private sink could not record "
                f"this handoff, so nothing would resume it: {exc}",
            ) from exc
        return ""


# ---------------------------------------------------------------------------
# sentinel (§5.7)
# ---------------------------------------------------------------------------
def write_sentinel(receipt: Mapping[str, Any]) -> Path:
    """Write the local sentinel for this (repo, branch), atomically."""
    path = contract.sentinel_path(str(receipt.get("repo") or ""), str(receipt.get("branch") or ""))
    _atomic_write_json(path, contract.sentinel_payload(receipt))
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
def _summary(receipt: Mapping[str, Any], verdict: contract.HandoffVerdict, sentinel: Path | None,
             published_ref: str, pull_url: str) -> str:
    snapshot = (
        f"{len(verdict.successes)} green, {len(verdict.pending)} still running, no red"
    )
    if verdict.ignored_spurious:
        snapshot += f" ({len(verdict.ignored_spurious)} known-spurious ignored)"
    lines = [
        f"Handoff accepted for pull request #{receipt['pr_number']} "
        f"({receipt['repo']}) at head {str(receipt['head_sha'])[:12]}: armed with "
        f"`{contract.MERGE_ON_GREEN_LABEL}`, base `{receipt['base_ref']}`, {snapshot}.",
        f"The `{contract.MERGE_OWNER}` sweeper owns the merge from here — it sweeps "
        "every 10 minutes and squash-merges once every check has CONCLUDED clean "
        "(the known-spurious `Workers Builds: macro` X excluded); a genuine red or a "
        "conflict gets `merge-blocked` plus one explanatory comment instead. This "
        "worker is done: make no further tool calls after the marker line below.",
    ]
    if pull_url:
        lines.append(f"Pull request: {pull_url}")
    if sentinel is not None:
        lines.append(f"Sentinel: {sentinel}")
    continuation = receipt.get("continuation") or {}
    if isinstance(continuation, Mapping) and continuation.get("continuation_id"):
        lines.append(
            f"Continuation {continuation['continuation_id']} resumes on "
            f"`{continuation.get('resume_on')}`"
            + (f" (recorded at {published_ref})" if published_ref else "")
        )
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel"))
    branch = _git(root, "branch", "--show-current")
    if not branch:
        raise _fail(
            EXIT_NOT_HANDOFFABLE,
            "detached-head",
            "this checkout is on a detached HEAD, so there is no branch a pull "
            "request could be tracking. Check out the working branch and re-run.",
        )
    head = _git(root, "rev-parse", "HEAD")
    repo = contract.normalize_repo(_git(root, "remote", "get-url", "origin"))
    if not repo:
        raise _fail(
            EXIT_INFRA,
            "origin-unresolved",
            "`git remote get-url origin` does not resolve to owner/name, so this "
            "handoff cannot be keyed to a repository.",
        )

    dirty = _dirty_entries(root)
    if dirty:
        raise _fail(
            EXIT_NOT_HANDOFFABLE,
            "uncommitted-work",
            "this checkout carries uncommitted work, so the pull request head is "
            "not the whole job: "
            + ", ".join(dirty[:8])
            + ("…" if len(dirty) > 8 else "")
            + ". Commit and push it first (entries under another fleet's worktree "
            "root are already excluded).",
        )

    remote_tip = _remote_branch_tip(root, branch)
    if not remote_tip:
        raise _fail(
            EXIT_NOT_HANDOFFABLE,
            "branch-not-pushed",
            f"branch `{branch}` does not exist on origin, so there is nothing for "
            "the sweeper to merge. Push it first.",
        )
    if remote_tip != head:
        raise _fail(
            EXIT_NOT_HANDOFFABLE,
            "remote-behind-local",
            f"origin/{branch} is at {remote_tip[:12]} but local HEAD is at "
            f"{head[:12]}: the sweeper would merge a head that is not this work. "
            "Push, then re-run.",
        )

    pull = _resolve_pull(branch, args.pr)
    number = pull.get("number")
    pull_url = str(pull.get("url") or "")
    state = str(pull.get("state") or "").upper()
    if state != "OPEN":
        raise _fail(
            EXIT_NOT_ARMED,
            "pull-request-not-open",
            f"pull request #{number} is {state or 'in an unknown state'}, not OPEN, "
            "so no sweeper will ever merge it.",
        )
    if bool(pull.get("isDraft")):
        raise _fail(
            EXIT_NOT_ARMED,
            "pull-request-is-draft",
            f"pull request #{number} is a DRAFT. The sweeper never merges a draft: "
            "mark it ready for review, then re-run.",
        )
    base_ref = str(pull.get("baseRefName") or "")
    if base_ref != REQUIRED_BASE_REF:
        raise _fail(
            EXIT_NOT_ARMED,
            "pull-request-wrong-base",
            f"pull request #{number} is based on `{base_ref or 'nothing'}`, not "
            f"`{REQUIRED_BASE_REF}`. The sweeper only merges into "
            f"`{REQUIRED_BASE_REF}`.",
        )

    remote_head = str(pull.get("headRefOid") or "")
    if not remote_head or remote_head != head:
        raise _fail(
            EXIT_NOT_HANDOFFABLE,
            "pull-request-head-mismatch",
            f"pull request #{number} has head {remote_head[:12] or '(unknown)'} but "
            f"local HEAD is {head[:12]}. The handoff covers exactly ONE head, and "
            "work done after it is covered by nothing — push, then re-run.",
        )

    labels = {
        str((label or {}).get("name") or "")
        for label in (pull.get("labels") or [])
        if isinstance(label, Mapping)
    }
    if contract.MERGE_ON_GREEN_LABEL not in labels:
        raise _fail(
            EXIT_NOT_ARMED,
            "pull-request-not-armed",
            f"pull request #{number} is not labeled `{contract.MERGE_ON_GREEN_LABEL}`, "
            "so nothing owns its merge and handing off would orphan the work. Run "
            f"`gh pr edit {number} --add-label {contract.MERGE_ON_GREEN_LABEL}`, then "
            "re-run.",
        )

    verdict = contract.classify_check_runs(_head_check_runs(repo, head))
    if verdict.state == "red":
        raise _fail(
            EXIT_RED,
            "head-carries-red-checks",
            f"pull request #{number}'s head carries concluded RED checks: "
            + ", ".join(verdict.red[:8])
            + ". The sweeper never merges a red, so nothing will pick this up: fix "
            "the cause and re-run the failed job (the label stays armed and the next "
            "sweep merges once the head is clean), or remove the "
            f"`{contract.MERGE_ON_GREEN_LABEL}` label and finish the merge by hand.",
        )
    if verdict.state == "unproven":
        raise _fail(
            EXIT_UNPROVEN,
            "head-unproven",
            f"pull request #{number}'s head is UNPROVEN: no considered check exists, "
            "or every considered check finished without a single success. An absence "
            "of red is not a pass — the sweeper will never merge this head either, so "
            "handing off here would orphan the work. Re-run the checks, or dispatch a "
            "run against this head, then re-run.",
        )

    base_sha = str(pull.get("baseRefOid") or "").strip()
    if not base_sha:
        try:
            base_sha = _git(root, "rev-parse", f"origin/{base_ref}")
        except HandoffError:
            base_sha = ""

    receipt = contract.build_receipt(
        repo=repo,
        pr_number=int(number),
        branch=branch,
        base_ref=base_ref,
        base_sha=base_sha,
        head_sha=head,
        verdict=verdict,
        accepted_at=_utc_now(),
        continuation_id=args.continuation_id,
        resume_on=args.resume_on,
        payload_ref=args.payload_ref,
    )

    published_ref = _publish(receipt, args.sink, bool(args.continuation_id))

    sentinel: Path | None = None
    try:
        sentinel = write_sentinel(receipt)
    except OSError as exc:
        # The receipt is already recorded and the marker still has to print: a
        # sentinel is a local convenience for `.claude/hooks/gh_quota_guard.py`,
        # not the handoff itself. Say so loudly rather than failing an accepted
        # handoff after the fact.
        _annotate_warning(
            "sentinel-write-failed",
            f"the local handoff sentinel could not be written ({exc}); the handoff "
            "itself stands.",
        )

    print(_summary(receipt, verdict, sentinel, published_ref, pull_url))
    if args.json:
        # A local terminal, not a public surface — the PRIVATE receipt in full.
        print(contract.compact_json(receipt))
    print(contract.terminal_marker(receipt), flush=True)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci_handoff.py",
        description=(
            "Take ONE finite snapshot of an armed pull request's head and print the "
            "terminal handoff marker. No polling, no waiting: the `merge-on-green` "
            "sweeper owns the merge from here."
        ),
        epilog=(
            "exit codes: 0 handed off; 2 red checks; 3 unproven head; "
            "4 dirty/unpushed/head mismatch; 5 no armed pull request; "
            "6 continuation sink failed; 7 gh/git/network failure."
        ),
    )
    parser.add_argument(
        "--pr",
        metavar="NUMBER",
        type=int,
        default=None,
        help="pull request to hand off (default: the open one for this branch)",
    )
    parser.add_argument(
        "--resume-on",
        choices=list(contract.RESUME_ON_CHOICES),
        default="merged",
        help="what the controller waits for before resuming (default: merged)",
    )
    parser.add_argument(
        "--continuation-id",
        metavar="ID",
        default=None,
        help="opaque id of the continuation to resume once the wait resolves",
    )
    parser.add_argument(
        "--payload-ref",
        metavar="PRIVATE_REF",
        default=None,
        help="private reference to the continuation payload — never a payload body",
    )
    parser.add_argument(
        "--sink",
        choices=list(SINK_CHOICES),
        default="auto",
        help="where the private receipt is recorded (default: auto)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="also print the full PRIVATE receipt as JSON before the marker",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return _run(args)
    except HandoffError as exc:
        _annotate_error(exc.slug, exc.message)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
