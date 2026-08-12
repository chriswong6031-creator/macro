#!/usr/bin/env python3
"""The pure contract for the terminal CI handoff — ``mastermind.ci_handoff.v1``.

WHY THIS EXISTS (operator directive, Wave A).
"System done" and "worker done" are different states. A worker that has pushed an
exact PR head and armed `merge-on-green` has finished its job; the sweeper owns
the merge from there. Before this module the release rule lived in exactly one
place — `_handoff_verdict` inside `.claude/hooks/ship_loop_guard.py` — which made
it a CLAUDE-shaped rule expressed as prose. Codex, a shell script, or a future
orchestrator had no way to ask the same question and get the same answer.

This module is that question, extracted whole. It has NO network calls, NO
subprocesses, and imports only the standard library, so both the Claude Stop hook
and the universal `scripts/ci_handoff.py` CLI can hold the identical classifier.
The pair silently disagreeing is how work gets orphaned: a session released on a
head the sweeper will refuse waits forever for a merge that never comes.

Keep this module free of repo imports. It is loaded BY FILE PATH from
`.claude/hooks/*.py` (never through `sys.path`), precisely so a hook can consult
the contract without acquiring the application import graph.

WHAT IT OWNS
------------
  * `is_spurious_check`   — the one known-spurious Cloudflare X, and nothing else.
  * `classify_check_runs` — armed / red / unproven, from a check-run listing.
  * `receipt_id`          — the deterministic handoff identity.
  * `build_receipt`       — the canonical PRIVATE receipt.
  * `public_receipt`      — the field-allowlisted PUBLIC projection, plus the
                            `assert_public_safe` leak gate that proves a private
                            field cannot reach a public surface.
  * `terminal_marker`     — the single parseable line that ends a worker's life.
  * `sentinel_*`          — the local sentinel path/shape shared by the CLI and
                            `.claude/hooks/gh_quota_guard.py`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Private receipt schema. Carries continuation routing; never published publicly.
SCHEMA = "mastermind.ci_handoff.v1"
#: Public projection schema. Safe for a PR comment or a check output.
PUBLIC_SCHEMA = "mastermind.ci_handoff.public.v1"
#: Controller event schema (see `event_idempotency_key`).
EVENT_SCHEMA = "mastermind.ci_event.v1"

#: The label that names the sweeper as merge owner. Must match
#: `.github/workflows/merge-on-green.yml` and `scripts/merge_on_green.py`.
MERGE_ON_GREEN_LABEL = "merge-on-green"
#: The merge owner recorded on every receipt. There is no second merge bot.
MERGE_OWNER = MERGE_ON_GREEN_LABEL

#: The worker state a receipt records. The worker is done; the system is not.
STATE_WAITING_CI = "WAITING_CI"

#: A CONCLUDED check outside this set is a genuine red. `neutral` and `skipped`
#: are not failures, but they are not proof either — see `classify_check_runs`.
NON_RED_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})

#: What `--resume-on` may say. `merged` is the default and the only one the
#: sweeper alone can satisfy; `live` additionally waits for deployment; `manual`
#: asks the controller for a human.
RESUME_ON_CHOICES = ("merged", "live", "manual")

#: Controller events the sink/listener must be able to carry (§5.10).
EVENT_KINDS = ("MERGED", "CI_FAILED", "MERGE_CONFLICT", "CI_INFRA_BLOCKED", "LIVE_CONFIRMED")

#: The terminal marker prefix. A worker prints exactly one line starting here and
#: then makes ZERO further tool calls.
MARKER_PREFIX = "CI_HANDOFF="


def is_spurious_check(name: str) -> bool:
    """The one known-spurious Cloudflare check every CI gate here has ignored.

    Deliberately narrow. `merge_on_green.py` and `ship_loop_guard.py` have always
    carried this exact predicate; broadening it would let a real red be waved
    through as noise, which is the single most expensive mistake this file can
    make. Widening the allowlist is a ruling, not a refactor.
    """
    lowered = str(name or "").lower()
    return "workers builds" in lowered and "macro" in lowered


@dataclass(frozen=True)
class HandoffVerdict:
    """The classification of one head's check runs.

    `state` is the decision; the four tuples are the evidence behind it and go
    into the receipt's `check_snapshot` verbatim.

    `red` entries are formatted ``"<name> (<conclusion>)"`` — a bare name cannot
    tell a `failure` from a `timed_out` from a `cancelled`, and a worker reading
    the block message needs that to know whether to re-run or to fix.
    `successes` and `pending` are bare names; there is nothing to disambiguate.
    """

    state: str
    successes: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()
    red: tuple[str, ...] = ()
    ignored_spurious: tuple[str, ...] = ()

    @property
    def is_armed(self) -> bool:
        return self.state == "armed"


def classify_check_runs(runs: Sequence[Mapping[str, Any]]) -> HandoffVerdict:
    """Classify a head's check runs into ``armed`` / ``red`` / ``unproven``.

    ``red``      — some considered check CONCLUDED outside `NON_RED_CONCLUSIONS`.
                   The sweeper never merges a red, so the worker must fix it or
                   disarm; naming the checks is the whole value of refusing here.
    ``armed``    — nothing concluded red, AND either something is still running
                   or something concluded `success`. The sweeper is a valid owner
                   of the remainder: a head still being proven is exactly what the
                   handoff exists to hand off.
    ``unproven`` — no considered check exists at all, or every considered check
                   has COMPLETED and none of them succeeded. An absence of red is
                   not a pass (#4779): a head whose only runs are `skipped`/
                   `neutral` has finished proving nothing, the sweeper will never
                   merge it, and releasing the worker there ORPHANS the work.

    Red OUTRANKS pending, the reverse of `decide_verdict` in
    `scripts/merge_on_green.py`. That asymmetry is deliberate and load-bearing:
    this verdict shapes a MESSAGE to a worker that can act on a red immediately,
    so telling it early is pure benefit, whereas the sweeper gates an irreversible
    merge plus a one-shot comment and therefore waits for full information.
    """
    considered: list[Mapping[str, Any]] = []
    ignored: list[str] = []
    for run in runs:
        name = str(run.get("name") or "unnamed check")
        if is_spurious_check(name):
            ignored.append(name)
        else:
            considered.append(run)

    spurious = tuple(ignored)
    if not considered:
        return HandoffVerdict("unproven", ignored_spurious=spurious)

    successes: list[str] = []
    pending: list[str] = []
    red: list[str] = []
    for run in considered:
        name = str(run.get("name") or "unnamed check")
        conclusion = run.get("conclusion")
        if run.get("status") != "completed":
            pending.append(name)
        elif conclusion not in NON_RED_CONCLUSIONS:
            red.append(f"{name} ({conclusion})")
        elif conclusion == "success":
            successes.append(name)

    if red:
        return HandoffVerdict(
            "red",
            successes=tuple(successes),
            pending=tuple(pending),
            red=tuple(red),
            ignored_spurious=spurious,
        )
    # Nothing red. Proof requires an affirmative pass OR something still running.
    if not pending and not successes:
        return HandoffVerdict("unproven", ignored_spurious=spurious)
    return HandoffVerdict(
        "armed",
        successes=tuple(successes),
        pending=tuple(pending),
        ignored_spurious=spurious,
    )


def repo_slug(repo: str) -> str:
    """The short, filesystem-safe name of ``owner/name`` — ``macro`` for this repo."""
    tail = str(repo or "").rstrip("/").split("/")[-1]
    if tail.endswith(".git"):
        tail = tail[: -len(".git")]
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "-", tail).strip("-")
    return cleaned or "repo"


def receipt_id(repo: str, pr_number: int, head_sha: str) -> str:
    """The deterministic handoff identity: ``cih_<repo>_<pr>_<head12>``.

    Pure and stable — the same (repo, pr, head) always yields the same id, which
    is what makes the sink idempotent and what lets a controller dedupe a replayed
    workflow event without keeping state. A new commit changes `head_sha` and
    therefore mints a new handoff, which is correct: the old one described a head
    that is no longer what the sweeper would merge.
    """
    head = re.sub(r"[^0-9a-fA-F]", "", str(head_sha or "")).lower()[:12]
    if not head:
        raise ValueError("receipt_id requires a head sha")
    return f"cih_{repo_slug(repo)}_{int(pr_number)}_{head}"


def build_receipt(
    *,
    repo: str,
    pr_number: int,
    branch: str,
    base_ref: str,
    base_sha: str,
    head_sha: str,
    verdict: HandoffVerdict,
    accepted_at: str,
    continuation_id: str | None = None,
    resume_on: str = "merged",
    payload_ref: str | None = None,
) -> dict[str, Any]:
    """The canonical PRIVATE receipt (§5.5). Never publish this object directly."""
    if resume_on not in RESUME_ON_CHOICES:
        raise ValueError(f"resume_on must be one of {RESUME_ON_CHOICES}, got {resume_on!r}")
    return {
        "schema": SCHEMA,
        "handoff_id": receipt_id(repo, pr_number, head_sha),
        "state": STATE_WAITING_CI,
        "repo": repo,
        "pr_number": int(pr_number),
        "branch": branch,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "accepted_at": accepted_at,
        "merge_owner": MERGE_OWNER,
        "check_snapshot": {
            "success": list(verdict.successes),
            "pending": list(verdict.pending),
            "red": list(verdict.red),
            "ignored_spurious": list(verdict.ignored_spurious),
        },
        "continuation": {
            "continuation_id": continuation_id,
            "resume_on": resume_on,
            "payload_ref": payload_ref,
        },
    }


#: EXACTLY the keys a public surface may carry. This is an allowlist that the
#: projection is BUILT from, never a denylist a private receipt is filtered
#: through — a filter silently passes any field someone adds later, an allowlist
#: silently drops it. `assert_public_safe` then re-proves the result independently.
PUBLIC_RECEIPT_FIELDS = (
    "schema",
    "handoff_id",
    "pr_number",
    "head_sha",
    "continuation_id",
    "resume_on",
)

#: Private receipt keys that must never appear on a public surface, by name.
PRIVATE_ONLY_FIELDS = (
    "payload_ref",
    "repo",
    "branch",
    "base_sha",
    "base_ref",
    "check_snapshot",
    "continuation",
    "merge_owner",
    "accepted_at",
)

#: Key fragments that smell like a credential or a prompt body. Checked against
#: public receipt KEYS so a future field named `..._token` cannot slip through.
_SECRET_KEY_RE = re.compile(
    r"token|secret|password|credential|cookie|session|bearer|api[_-]?key"
    r"|prompt|payload|context|transcript|note|body|path|dir|file",
    re.I,
)
#: Value shapes that leak a private location: the control-plane URI scheme, an
#: absolute POSIX path, a home-relative path, or a Windows drive path.
_PRIVATE_VALUE_RE = re.compile(r"^(?:private://|/|~/|[A-Za-z]:[\\/])")


def public_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """The PUBLIC projection of a receipt — built from `PUBLIC_RECEIPT_FIELDS` only.

    Safe for a PR comment, a check output, or the terminal marker. It carries an
    opaque continuation IDENTIFIER and nothing else about the continuation: no
    prompt body, no private file path, no strategy context. Macro is a public
    repository (§2.4) and everything on it is world-readable forever.
    """
    continuation = receipt.get("continuation") or {}
    if not isinstance(continuation, Mapping):
        continuation = {}
    projected = {
        "schema": PUBLIC_SCHEMA,
        "handoff_id": receipt.get("handoff_id"),
        "pr_number": receipt.get("pr_number"),
        "head_sha": receipt.get("head_sha"),
        "continuation_id": continuation.get("continuation_id"),
        "resume_on": continuation.get("resume_on"),
    }
    assert_public_safe(projected)
    return projected


def assert_public_safe(mapping: Mapping[str, Any]) -> None:
    """Raise `ValueError` if `mapping` could leak private context onto a public surface.

    Three independent gates, because the projection above and this check must be
    able to catch each other's mistakes:
      1. no key outside `PUBLIC_RECEIPT_FIELDS`;
      2. no key that is a known private-only field or that smells like a secret;
      3. no string value shaped like a private URI or a filesystem path.
    Nested containers are rejected outright — a public receipt is flat scalars,
    and a nested object is the shape a payload body would arrive in.
    """
    for key, value in mapping.items():
        name = str(key)
        if name not in PUBLIC_RECEIPT_FIELDS:
            raise ValueError(f"public receipt carries non-public field {name!r}")
        if name in PRIVATE_ONLY_FIELDS or _SECRET_KEY_RE.search(name):
            raise ValueError(f"public receipt carries private-only field {name!r}")
        if isinstance(value, (Mapping, list, tuple, set)):
            raise ValueError(f"public receipt field {name!r} is a container, not a scalar")
        if isinstance(value, str) and _PRIVATE_VALUE_RE.match(value):
            raise ValueError(f"public receipt field {name!r} leaks a private location")


def compact_json(value: Any) -> str:
    """Canonical one-line JSON: sorted keys, tight separators, no embedded newline."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def marker_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """The public projection plus `state` — everything the marker line carries."""
    payload = public_receipt(receipt)
    payload["state"] = receipt.get("state") or STATE_WAITING_CI
    return payload


def terminal_marker(receipt: Mapping[str, Any]) -> str:
    """The single parseable line that ends a worker's life.

    ONE line, public-safe, machine-first. The orchestrator matches `MARKER_PREFIX`
    at the start of a line and deallocates the model; a human-readable paragraph
    may accompany it but must never wrap it, because a marker split across lines
    is a marker the controller cannot see.
    """
    payload = marker_payload(receipt)
    assert_public_safe({k: v for k, v in payload.items() if k != "state"})
    line = MARKER_PREFIX + compact_json(payload)
    if "\n" in line or "\r" in line:  # pragma: no cover - compact_json forbids it
        raise ValueError("terminal marker must be exactly one line")
    return line


def parse_terminal_marker(text: str) -> dict[str, Any] | None:
    """The first well-formed `CI_HANDOFF=` line in `text`, or None.

    The controller's half of `terminal_marker`. Tolerates surrounding prose so a
    worker may print an explanation alongside the marker.
    """
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line.startswith(MARKER_PREFIX):
            continue
        try:
            parsed = json.loads(line[len(MARKER_PREFIX):])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def event_idempotency_key(repo: str, pr_number: int, head_sha: str, event: str) -> str:
    """The natural controller-event key: ``repo:pr:head:EVENT`` (§5.10).

    A duplicate workflow delivery must not create a duplicate continuation task,
    and `(repo, pr_number, head_sha, event)` is the tuple that makes two
    deliveries of the same fact indistinguishable.
    """
    return f"{repo_slug(repo)}:{int(pr_number)}:{str(head_sha or '').lower()}:{event}"


# --------------------------------------------------------------------------
# Local sentinel (§5.7) — shared by scripts/ci_handoff.py and the quota guard.
# --------------------------------------------------------------------------

#: Full override for the sentinel root. Follows the house convention already set
#: by `engine/marketing/reply_queue.state_dir` (MASTERMIND_REPLY_DESK_DIR).
SENTINEL_DIR_ENV = "MASTERMIND_CI_HANDOFF_DIR"


def sentinel_root(state_root: str | os.PathLike[str] | None = None) -> Path:
    """Where sentinels live — always OUTSIDE the repository checkout.

    A sentinel inside the tree would show up in `git status`, gate the ship loop,
    and eventually get committed to a public repo. `~/.mastermind/ci_handoffs` is
    the same private HOST state root the marketing reply desk already uses.
    """
    if state_root is not None:
        return Path(state_root).expanduser()
    override = os.environ.get(SENTINEL_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".mastermind" / "ci_handoffs"


def _digest(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def sentinel_path(
    repo: str, branch: str, state_root: str | os.PathLike[str] | None = None
) -> Path:
    """``<private-state>/ci_handoffs/<repo-hash>/<branch-hash>.json``.

    Keyed on the REMOTE repo and the branch, not on the local checkout path, so a
    sentinel written from one worktree is visible from another worktree of the
    same branch — the two share exactly one PR and exactly one merge owner.
    """
    return sentinel_root(state_root) / _digest(repo) / f"{_digest(branch)}.json"


def sentinel_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """The six facts a sentinel carries (§5.7). No continuation, no check detail."""
    return {
        "repo": receipt.get("repo"),
        "branch": receipt.get("branch"),
        "head_sha": receipt.get("head_sha"),
        "pr_number": receipt.get("pr_number"),
        "handoff_id": receipt.get("handoff_id"),
        "accepted_at": receipt.get("accepted_at"),
    }


def sentinel_matches(
    data: Mapping[str, Any] | None, repo: str, branch: str, head_sha: str
) -> bool:
    """Whether a loaded sentinel still applies to (repo, branch, head).

    All three must match. A new commit moves HEAD and therefore invalidates the
    sentinel automatically — which is the point: the worker handed off ONE head,
    and work done after that head is not covered by anything.
    """
    if not isinstance(data, Mapping):
        return False
    return (
        str(data.get("repo") or "") == str(repo or "")
        and str(data.get("branch") or "") == str(branch or "")
        and str(data.get("head_sha") or "").lower() == str(head_sha or "").lower()
        and bool(data.get("handoff_id"))
    )


def read_sentinel(
    repo: str, branch: str, state_root: str | os.PathLike[str] | None = None
) -> dict[str, Any] | None:
    """The sentinel for (repo, branch), or None. Never raises — callers fail open."""
    try:
        raw = sentinel_path(repo, branch, state_root).read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def active_sentinel(
    repo: str, branch: str, head_sha: str, state_root: str | os.PathLike[str] | None = None
) -> dict[str, Any] | None:
    """The sentinel for (repo, branch) when it still matches `head_sha`, else None."""
    data = read_sentinel(repo, branch, state_root)
    return data if sentinel_matches(data, repo, branch, head_sha) else None


def normalize_repo(remote_url: str) -> str:
    """``owner/name`` from any git remote URL shape, or ``""`` when unrecognizable.

    Handles `https://host/owner/name(.git)`, `ssh://git@host/owner/name`,
    `git@host:owner/name.git`, and a bare local path (which yields "", because a
    local clone has no canonical owner and a wrong guess would key a sentinel to
    a repo identity that does not exist).
    """
    url = str(remote_url or "").strip()
    if not url:
        return ""
    if url.endswith(".git"):
        url = url[: -len(".git")]
    scp = re.match(r"^[A-Za-z0-9_.-]+@([^:/]+):(.+)$", url)
    if scp:
        path = scp.group(2)
    else:
        stripped = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)
        if stripped == url and not url.startswith("/"):
            path = url
        elif stripped == url:
            return ""
        else:
            path = stripped.split("/", 1)[1] if "/" in stripped else ""
    parts = [p for p in str(path).strip("/").split("/") if p]
    if len(parts) < 2:
        return ""
    return "/".join(parts[-2:])


def iter_check_names(runs: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Every check-run name in listing order. Diagnostics only."""
    return tuple(str(run.get("name") or "unnamed check") for run in runs)
