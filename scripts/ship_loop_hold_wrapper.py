#!/usr/bin/env python3
"""Bounded HOLD-FOR-SOL state adapter in front of the completion guard.

The main completion guard deliberately treats an ordinary unmerged PR as unfinished.
That remains correct. A different state exists in repository law, however: Sol/CEO
may explicitly order a specific PR held for review. DEC:SOL-HOLD-IS-A-MERGE-BARRIER
then requires the PR to be draft, disarmed, and unmerged. Waiting for that prohibited
merge is unsatisfiable and used to make Claude repeat ``SHIP LOOP BLOCKED`` until the
generic ten-block escape ladder fired.

This front-end is intentionally narrow and fail-closed. It probes only two shapes:
an ordinary ``unmerged`` hold candidate on a sanctioned ``claude/*`` branch, or a
local branch in Sol's ``sol/*`` authority namespace. The latter is recognized before
the canonical guard emits its first ``unsafe_branch`` response, because even one
false rename-oriented instruction can mutate the identity of an explicitly held PR.
Normal non-Sol sessions pay only a local branch-name read and never spend GitHub quota
unless the canonical guard has already reached ``unmerged``.

A candidate must still prove the exact pushed head, a clean worktree, a draft PR whose
title starts ``HOLD-FOR-SOL``, no ``merge-on-green`` label, no native auto-merge,
recorded Sol authority and Sol release condition, and binding check evidence. A
concluded-green candidate becomes ``SHIP LOOP PARKED``. For the special ``sol/*``
case only, a valid hold whose checks are still pending or red is intercepted before
the ordinary branch-law message: pending checks produce a non-terminal HOLD wait and
red checks produce a HOLD repair block, both explicitly forbidding branch/PR identity
mutation. Every malformed/ambiguous hold and every non-``sol/*`` unsafe branch
delegates byte-for-byte to the canonical guard. Ordinary branch, merge, CI, render,
and live enforcement therefore remains unchanged.

PARKED is narrated ONCE per frozen hold state (Sol commission #6379). This
adapter used to be stateless, so every later Stop — typically a turn started by
a leftover background task's ``<task-notification>`` — re-probed GitHub and
re-emitted the full PARKED message, making a correctly parked worker look stuck
(incident PR #6371). The first PARKED verdict now writes a ``parked_latch``
(``parked:<pr>:<head>``) into the guard's own per-session state ledger; a later
Stop that re-derives the IDENTICAL parked state passes silently. The latch never
weakens the gate: every quiet pass still runs the full mechanical hold probe, so
a released hold, a new head, a re-armed label, a dirtied tree, or a check that
stopped being green makes the probe answer differently, clears the latch, and
restores ordinary fail-closed law.

An UNANSWERABLE probe silences nothing (red-team F1/F2, 2026-08-24). A local
git failure inside the probe reads as "not a hold candidate" and delegates —
that is how a session whose held PR was merged and whose branch was pruned
falls through to the canonical guard's merged-PR/CI/render/live chain instead
of stopping silently on a stale latch. A GitHub-layer failure raises
``HoldProbeUnanswerable`` and ALSO delegates: the canonical guard files its own
escapeable ``github_unreachable``/``github_rate_limited`` block, exactly as
before this adapter existed, because an outage cannot prove the hold is still
in force — a released hold looks locally identical to a parked one. The latch
is kept across unanswerable Stops (it re-silences once the probe answers
"parked" again) but it is never itself evidence.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


HOLD_TOKEN = "HOLD-FOR-SOL"
MERGE_LABEL = "merge-on-green"
_PROTOCOL_FIELDS = ("Authority", "Release condition")


class HoldProbeUnanswerable(RuntimeError):
    """The GitHub layer could not answer the hold probe.

    Deliberately distinct from every local failure: a local git error means
    "this is not (or no longer) a hold-candidate worktree" and reads as probe
    None, while this exception means "the candidate shape holds locally but
    the remote truth is unknowable right now". Neither may silence a Stop —
    the difference only decides whether the parked latch is cleared (local
    evidence of change) or kept (pure outage, latch re-silences once the
    probe answers parked again)."""


def _read_payload() -> tuple[dict[str, Any] | None, bytes]:
    raw = sys.stdin.buffer.read()
    if not raw:
        return None, raw
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, raw
    return (payload if isinstance(payload, dict) else None), raw


def _load_guard(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("ship_loop_guard_delegate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load completion guard at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _relay(delegate: Path, raw: bytes, cwd: Path | None) -> None:
    proc = subprocess.run(
        [sys.executable, "-u", str(delegate)],
        input=raw,
        cwd=str(cwd or Path.cwd()),
        env=os.environ.copy(),
        capture_output=True,
        check=False,
    )
    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
        sys.stdout.flush()
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
        sys.stderr.flush()
    raise SystemExit(int(proc.returncode))


def _git(root: Path, *args: str, timeout: int = 5) -> str:
    proc = subprocess.run(
        ("git", *args),
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail[:300]}")
    return proc.stdout.strip()


def _plain(text: str) -> str:
    # Hold records are Markdown. Strip formatting punctuation so ``**Authority:**``
    # and ``Authority:`` are the same protocol token without widening prose matching.
    return re.sub(r"[*_`#>]", "", text or "")


def _field(text: str, name: str) -> str:
    """Extract one hold-protocol field whether line-oriented or inline.

    Real PR #6138 records ``Authority: ... Release condition: ...`` on one line in
    both the body and the hold comment. Requiring a line-start field silently made
    the terminal state unreachable for the incident it was built to fix. The next
    known protocol label (or end of text) bounds the value; arbitrary prose labels do
    not. The surrounding HOLD token / draft / disarm checks remain the authority gate.
    """
    labels = "|".join(re.escape(label) for label in _PROTOCOL_FIELDS)
    match = re.search(
        rf"(?is)(?<!\w){re.escape(name)}\s*:\s*(.+?)(?=\s*(?:(?<!\w)(?:{labels})\s*:|$))",
        text or "",
    )
    return match.group(1).strip() if match else ""


def _hold_protocol_is_complete(pull: dict[str, Any], comments: list[dict[str, Any]]) -> bool:
    title = str(pull.get("title") or "").strip()
    if not title.upper().startswith(HOLD_TOKEN):
        return False
    if pull.get("draft") is not True:
        return False
    labels = {str((label or {}).get("name") or "") for label in (pull.get("labels") or [])}
    if MERGE_LABEL in labels:
        return False
    if pull.get("auto_merge") is not None:
        return False

    text = _plain(
        "\n".join(
            [
                str(pull.get("body") or ""),
                *(str(comment.get("body") or "") for comment in comments if isinstance(comment, dict)),
            ]
        )
    )
    lowered = text.lower()
    if HOLD_TOKEN.lower() not in lowered or "do not merge" not in lowered:
        return False
    authority = _field(text, "Authority")
    release = _field(text, "Release condition")
    # HOLD-FOR-SOL is not a generic user-authored defer label. Both sides of the
    # protocol must bind the stop to Sol so a session cannot invent a vague hold
    # and use it as an escape hatch from the ordinary unmerged contract.
    if not authority or not re.search(r"\bsol\b", authority, flags=re.IGNORECASE):
        return False
    if not release or not re.search(r"\bsol\b", release, flags=re.IGNORECASE):
        return False
    return True


def _hold_probe(guard: ModuleType, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a fully authenticated hold candidate without granting an exit.

    ``status`` is ``parked`` only when all binding checks are concluded green.
    ``pending`` and ``red`` are actionable only for the ``sol/*`` authority-branch
    interception in ``main``; ordinary ``claude/*`` behavior still delegates unless
    the hold is fully PARKED.
    """
    # Every failure in this LOCAL section — an unresolvable root/state, a git
    # that answers non-zero (a pruned @{upstream} after Sol merges the held PR
    # is the canonical case), a malformed ledger — reads as "not a hold
    # candidate" and returns None, which delegates to the fail-closed guard.
    # Only the GitHub layer below may raise HoldProbeUnanswerable.
    try:
        root = guard._repo_root(payload)
        if root is None:
            return None
        root = Path(root)
        state = guard._load(guard._state_path(root, payload))
        if not isinstance(state, dict):
            return None
        last_blocker = str(state.get("last_blocker") or "")
        parked_latch = str(state.get("parked_latch") or "")

        # Read the local branch before deciding whether GitHub deserves a probe. A Sol
        # authority branch is the one case where waiting for a prior unsafe_branch is
        # itself unsafe: the first false message can cause the worker to rename the held
        # branch and GitHub closes/rekeys the PR. All other branches preserve the old
        # quota rule and are eligible only after the canonical guard reaches unmerged.
        branch = _git(root, "branch", "--show-current")
        if branch.startswith("sol/"):
            candidate_kind = "sol_authority"
        elif last_blocker == "unmerged" and branch.startswith("claude/"):
            candidate_kind = "ordinary_unmerged"
        elif parked_latch.startswith("parked:") and branch.startswith("claude/"):
            # A delegated GitHub outage legitimately changes last_blocker to
            # github_unreachable. The exact parked latch remains the durable
            # candidate identity until positive local/remote evidence changes
            # it; transport ambiguity alone may not erase that identity.
            candidate_kind = "ordinary_latched"
        else:
            return None

        head = _git(root, "rev-parse", "HEAD")
        if candidate_kind == "ordinary_latched":
            latch_parts = parked_latch.split(":")
            if len(latch_parts) != 3 or latch_parts[2] != head:
                return None
        upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
        if int(_git(root, "rev-list", "--count", f"{upstream}..HEAD") or "0") != 0:
            return None
        # A Sol preflight can run before the delegate's first Stop verdict, so cleanliness
        # must be proven here rather than inferred from prior state.
        if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
            return None

        owner, repo = guard._github_slug(root)
    except Exception:
        return None

    try:
        pull = guard._open_pull(owner, repo, branch)
    except Exception as exc:
        raise HoldProbeUnanswerable(str(exc)) from exc
    if not isinstance(pull, dict):
        return None
    number = pull.get("number")
    if str((pull.get("head") or {}).get("sha") or "") != head:
        return None

    comments_url = str(pull.get("comments_url") or "")
    try:
        comments = guard._get_json(comments_url) if comments_url else []
    except Exception as exc:
        raise HoldProbeUnanswerable(str(exc)) from exc
    if not isinstance(comments, list) or not _hold_protocol_is_complete(pull, comments):
        return None

    try:
        runs = guard._head_check_runs(owner, repo, head)
    except Exception as exc:
        raise HoldProbeUnanswerable(str(exc)) from exc
    red, pending, passed = guard._split_head_runs(runs)
    if red:
        status = "red"
    elif pending or not passed:
        # No concluded-green binding check is evidence-incomplete, not permission
        # to PARK. Treat it like pending so the Sol authority branch cannot fall
        # back to the misleading rename-oriented unsafe_branch message.
        status = "pending"
    else:
        status = "parked"

    return {
        "number": number,
        "branch": branch,
        "head": head,
        "candidate_kind": candidate_kind,
        "source_blocker": last_blocker,
        "status": status,
        "red": red,
        "pending": pending,
        "passed": passed,
    }


def _parked_hold(guard: ModuleType, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Backward-compatible terminal view used by the canonical regression suite."""
    probe = _hold_probe(guard, payload)
    if probe is None or probe["status"] != "parked":
        return None
    return {
        "number": probe["number"],
        "branch": probe["branch"],
        "head": probe["head"],
        "passed": probe["passed"],
    }


def _hold_block(probe: dict[str, Any]) -> dict[str, str] | None:
    """Return the non-terminal block for a valid Sol authority hold, if any."""
    if probe.get("candidate_kind") != "sol_authority" or not str(probe.get("branch") or "").startswith("sol/"):
        return None
    status = probe.get("status")
    if status == "pending":
        pending = ", ".join(str(name) for name in probe.get("pending", [])[:8]) or "binding checks not yet concluded"
        return {
            "decision": "block",
            "reason": (
                f"HOLD-FOR-SOL WAITING: PR #{probe['number']} is a ratified Sol hold on "
                f"{probe['branch']}; exact head {str(probe['head'])[:12]} is pushed and clean, "
                f"but checks are not yet complete ({pending}). Do not rename the branch, "
                "close/reopen the PR, arm merge-on-green, merge, render, or mutate PR identity. "
                "Wait for the existing check watcher only. If checks conclude green this state "
                "becomes terminal PARKED; if a binding check concludes red, repair that check "
                "without treating the Sol authority branch as the blocker."
            ),
        }
    if status == "red":
        red = ", ".join(str(name) for name in probe.get("red", [])[:8]) or "binding check failure"
        return {
            "decision": "block",
            "reason": (
                f"HOLD-FOR-SOL CHECKS RED: PR #{probe['number']} remains held and must not merge. "
                f"Binding checks are red ({red}). Repair the failing check on the same held PR; "
                "do not rename the Sol authority branch, close/reopen the PR, arm merge-on-green, "
                "or use branch mutation as a ship-loop escape. A new exact head must earn its own "
                "green binding proof before it can become PARKED."
            ),
        }
    return None


def _ledger(guard: ModuleType, payload: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    """This session's guard state file and its parsed content, best-effort.

    The latch is bookkeeping inside the guard's existing per-session ledger,
    never a second lifecycle store. A session the guard has not baselined (no
    ledger) simply cannot latch — PARKED then narrates on every Stop exactly as
    before this repair, which is the harmless direction.
    """
    try:
        root = guard._repo_root(payload)
        if root is None:
            return None, None
        path = guard._state_path(Path(root), payload)
        state = guard._load(path)
        return path, (state if isinstance(state, dict) else None)
    except Exception:
        return None, None


def _update_ledger(guard: ModuleType, path: Path | None, mutate: Any) -> Any:
    """Use the guard's coherent per-session ledger transaction, or do nothing.

    A wrapper/guard revision mismatch must never fall back to saving a stale
    whole-ledger snapshot. Missing transaction support therefore loses only
    the narration latch (the documented harmless direction); ordinary Stop
    enforcement still delegates unchanged.
    """
    if path is None:
        return None
    updater = getattr(guard, "_update_ledger", None)
    if not callable(updater):
        return None
    try:
        return updater(path, mutate)
    except Exception:
        return None


def _parked_message(probe: dict[str, Any]) -> dict[str, str]:
    checks = ", ".join(str(name) for name in probe["passed"][:8])
    return {
        "systemMessage": (
            f"SHIP LOOP PARKED: PR #{probe['number']} is lawfully {HOLD_TOKEN}. "
            "The exact local head is pushed; the worktree is clean; the PR is "
            "draft; merge-on-green and native auto-merge are disarmed; Sol "
            "authority plus Sol release condition are recorded; and all binding "
            f"checks have concluded clean ({checks}). Merge/render/live are "
            "intentionally deferred to Sol review. This is a terminal PARKED "
            "state, not SHIPPED and not a blocker to retry. Do not re-enter the "
            "ship loop unless Sol releases the hold. This is the ONE terminal "
            "report: create no new ship watchers or wake timers, and if a "
            "leftover background task completes later, end that turn without "
            "re-reporting — this guard stays silent for the same frozen hold."
        )
    }


def _handle_stop(guard: ModuleType, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve one Stop against the hold law; None means delegate to the guard.

    Returns ``{"action": "silent"}`` for a latched terminal state that has
    nothing new to say, or ``{"action": "emit", "value": <hook JSON>}`` for the
    single PARKED report and the non-terminal sol/* hold blocks.

    Only a probe that POSITIVELY answers "parked" for the exact latched
    identity may silence a Stop. An unanswerable GitHub layer delegates with
    the latch kept (the canonical guard files its own escapeable external
    block; the latch re-silences once the probe answers parked again), and
    every positively-changed or no-longer-candidate state clears the latch and
    delegates — a released hold resumes the ordinary fail-closed ship loop,
    never a suppressed one (red-team F1/F2, 2026-08-24).
    """
    path, state = _ledger(guard, payload)
    latched = str((state or {}).get("parked_latch") or "")

    try:
        probe = _hold_probe(guard, payload)
    except HoldProbeUnanswerable:
        # GitHub cannot answer. This wrapper may never replace an ambiguous
        # state with permission to stop — and it also may not clear a ratified
        # latch on evidence of nothing. Delegate; the guard owns outage blocks.
        return None
    except Exception:
        # A crash in the probe itself restores the original guard unchanged.
        return None

    if probe is not None and probe["status"] == "parked":
        key = f"parked:{probe['number']}:{probe['head']}"
        def latch(latest: dict[str, Any]) -> str:
            if str(latest.get("parked_latch") or "") == key:
                return "already"
            latest["parked_latch"] = key
            return "written"

        latch_result = _update_ledger(guard, path, latch)
        if latch_result == "already":
            # Same frozen hold, already narrated once: quiescent pass. This is
            # what makes a leftover background task's wake turn end silently.
            return {"action": "silent"}
        if latch_result is None and latched == key:
            # A pre-transaction delegate can still read an existing latch. It
            # may silence that exact mechanically re-proven state, but it may
            # not write and risk erasing a concurrent watcher.
            return {"action": "silent"}
        return {"action": "emit", "value": _parked_message(probe)}

    if state is not None and path is not None:
        # The hold state positively moved (released, re-armed, red, pending,
        # new head, dirty tree, closed PR, or the worktree stopped being a
        # candidate at all): any latch in the CURRENT locked ledger names a
        # state that no longer exists. The pre-probe snapshot may not have seen
        # a concurrent latch, so the transaction itself decides whether there
        # is one to clear. Ordinary fail-closed law then gates fresh.
        _update_ledger(guard, path, lambda latest: latest.pop("parked_latch", None))

    if probe is not None:
        hold_block = _hold_block(probe)
        if hold_block is not None:
            return {"action": "emit", "value": hold_block}
    return None


def main() -> None:
    payload, raw = _read_payload()
    delegate = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "ship_loop_guard.py"
    )
    if payload is None:
        _relay(delegate, raw, None)

    cwd = Path(str(payload.get("cwd") or Path.cwd())).expanduser()
    if str(payload.get("hook_event_name") or "") == "Stop":
        verdict: dict[str, Any] | None = None
        try:
            guard = _load_guard(delegate)
            verdict = _handle_stop(guard, payload)
        except Exception:
            verdict = None
        if verdict is not None:
            if verdict.get("action") == "emit":
                print(json.dumps(verdict["value"], ensure_ascii=False))
            return

    _relay(delegate, raw, cwd)


if __name__ == "__main__":
    main()
