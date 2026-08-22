#!/usr/bin/env python3
"""Bounded HOLD-FOR-SOL state adapter in front of the completion guard.

The main completion guard deliberately treats an ordinary unmerged PR as unfinished.
That remains correct. A different state exists in repository law, however: Sol/CEO
may explicitly order a specific PR held for review. DEC:SOL-HOLD-IS-A-MERGE-BARRIER
then requires the PR to be draft, disarmed, and unmerged. Waiting for that prohibited
merge is unsatisfiable and used to make Claude repeat ``SHIP LOOP BLOCKED`` until the
generic ten-block escape ladder fired.

This front-end is intentionally narrow and fail-closed. It only probes for a lawful
hold after the existing guard has already reached one hold-candidate blocker:
ordinary ``unmerged`` on a sanctioned ``claude/*`` branch, or ``unsafe_branch`` on
Sol's ``sol/*`` authority namespace. It then requires the exact pushed head, a clean
worktree, a draft PR whose title starts ``HOLD-FOR-SOL``, no ``merge-on-green`` label,
no native auto-merge, recorded Sol authority and Sol release condition, and binding
check evidence.

A concluded-green candidate becomes ``SHIP LOOP PARKED``. For the special ``sol/*``
case only, a valid hold whose checks are still pending or red is intercepted before
the ordinary branch-law message: pending checks produce a non-terminal HOLD wait and
red checks produce a HOLD repair block, both explicitly forbidding branch/PR identity
mutation. This matters because telling a ratified hold that its branch is unsafe made
agents try to rename the held branch, which closes/rekeys the PR instead of advancing
the lawful hold. Every malformed/ambiguous hold and every non-``sol/*`` unsafe branch
delegates byte-for-byte to the canonical guard. Ordinary branch, merge, CI, render,
and live enforcement therefore remains unchanged.
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
    root = guard._repo_root(payload)
    if root is None:
        return None
    root = Path(root)
    state = guard._load(guard._state_path(root, payload))
    # Do not spend shared GitHub quota on every Stop. The ordinary guard must first
    # reach a state that can be a lawful hold. ``unmerged`` is the sanctioned
    # claude/* path; ``unsafe_branch`` is considered only for Sol's own sol/*
    # authority namespace. Any other blocker still belongs entirely to the delegate.
    if not isinstance(state, dict):
        return None
    last_blocker = str(state.get("last_blocker") or "")
    if last_blocker not in {"unmerged", "unsafe_branch"}:
        return None

    branch = _git(root, "branch", "--show-current")
    if last_blocker == "unmerged":
        if not branch.startswith("claude/"):
            return None
    elif not branch.startswith("sol/"):
        # Preserve the branch-law incident repair: codex/*, claire/*, bare names,
        # and every other unsafe delivery namespace remain unsafe even when a PR
        # happens to contain hold-shaped prose. This exception is only for a
        # ratified Sol authority branch that cannot be renamed without mutating
        # the held PR's identity/state.
        return None

    head = _git(root, "rev-parse", "HEAD")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    if int(_git(root, "rev-list", "--count", f"{upstream}..HEAD") or "0") != 0:
        return None
    # The prior guard verdict proved the tree clean at that Stop. Recheck now so
    # edits made after the block can never be laundered by the hold adapter.
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        return None

    owner, repo = guard._github_slug(root)
    pull = guard._open_pull(owner, repo, branch)
    if not isinstance(pull, dict):
        return None
    number = pull.get("number")
    if str((pull.get("head") or {}).get("sha") or "") != head:
        return None

    comments_url = str(pull.get("comments_url") or "")
    comments = guard._get_json(comments_url) if comments_url else []
    if not isinstance(comments, list) or not _hold_protocol_is_complete(pull, comments):
        return None

    runs = guard._head_check_runs(owner, repo, head)
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
    if probe.get("source_blocker") != "unsafe_branch" or not str(probe.get("branch") or "").startswith("sol/"):
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
        try:
            guard = _load_guard(delegate)
            probe = _hold_probe(guard, payload)
        except Exception:
            # Any uncertainty restores the original fail-closed guard. This wrapper
            # may correct the reason for one proven hold state; it may never replace
            # an ambiguous ordinary guard error with permission to stop.
            probe = None
        if probe is not None and probe["status"] == "parked":
            checks = ", ".join(str(name) for name in probe["passed"][:8])
            print(
                json.dumps(
                    {
                        "systemMessage": (
                            f"SHIP LOOP PARKED: PR #{probe['number']} is lawfully {HOLD_TOKEN}. "
                            "The exact local head is pushed; the worktree is clean; the PR is "
                            "draft; merge-on-green and native auto-merge are disarmed; Sol "
                            "authority plus Sol release condition are recorded; and all binding "
                            f"checks have concluded clean ({checks}). Merge/render/live are "
                            "intentionally deferred to Sol review. This is a terminal PARKED "
                            "state, not SHIPPED and not a blocker to retry. Do not re-enter the "
                            "ship loop unless Sol releases the hold."
                        )
                    },
                    ensure_ascii=False,
                )
            )
            return
        if probe is not None:
            hold_block = _hold_block(probe)
            if hold_block is not None:
                print(json.dumps(hold_block, ensure_ascii=False))
                return

    _relay(delegate, raw, cwd)


if __name__ == "__main__":
    main()
