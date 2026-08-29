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
concluded-green candidate becomes ``SHIP LOOP PARKED``.

A valid hold whose checks are still pending or red is intercepted for BOTH candidate
kinds: pending checks produce a non-terminal HOLD wait and red checks produce a HOLD
repair block, both explicitly forbidding branch/PR identity mutation. Before
2026-08-28 that interception was ``sol/*``-only, so an ordinary ``claude/*`` hold was
told to squash-merge a PR that repository law forbids merging for the whole pre-green
window (121 consecutive such blocks on PR #6608). The interception is a *message*
correction, never a permission one — both paths still block, and ``parked`` remains
the sole terminal exit and still demands every binding check concluded green.

Every malformed/ambiguous hold and every non-``sol/*`` unsafe branch delegates
byte-for-byte to the canonical guard. Ordinary branch, merge, CI, render, and live
enforcement therefore remains unchanged.
PARKED is narrated once per frozen hold identity. Pending holds share the canonical
``ci_quiescence.v1`` record and its already-owned watcher; this wrapper does not add
a watcher, database, scheduler, queue, retry lane, or lifecycle. An identical wait
therefore takes the guard's local no-GitHub fast path, while a dead watcher, changed
head, changed hold authority, green, or red is classified exactly once. A GitHub
failure is never hold proof and always delegates fail-closed.
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
    """The remote layer could not answer; neither PARKED nor quiet is proven."""


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
    ``pending`` and ``red`` remain nonterminal for both sanctioned branch shapes;
    the wrapper preserves the #6626 HOLD WAITING/CHECKS RED messages and may put
    only an already-watched pending head into the shared quiescence ledger.
    """
    # Local failures mean this is not (or is no longer) a candidate. Remote
    # failures are different: they prove nothing and must preserve any existing
    # latch while the canonical guard reports its own outage block.
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
        quiescence = state.get("ci_quiescence")

        # Read the local branch before deciding whether GitHub deserves a probe.
        # An already-minted hold wait is also a lawful candidate after entry has
        # cleared last_blocker; the record is never sufficient by itself because
        # the full pushed/clean/remote hold protocol is re-proven below.
        branch = _git(root, "branch", "--show-current")
        if branch.startswith("sol/"):
            candidate_kind = "sol_authority"
        elif last_blocker == "unmerged" and branch.startswith("claude/"):
            candidate_kind = "ordinary_unmerged"
        elif parked_latch.startswith("parked:") and branch.startswith("claude/"):
            candidate_kind = "ordinary_latched"
        elif (
            isinstance(quiescence, dict)
            and quiescence.get("mode") == "hold"
            and branch.startswith("claude/")
        ):
            candidate_kind = "ordinary_quiescent"
        else:
            return None

        head = _git(root, "rev-parse", "HEAD")
        if candidate_kind == "ordinary_latched":
            latch_parts = parked_latch.split(":")
            if len(latch_parts) != 3 or latch_parts[2] != head:
                return None
        if candidate_kind == "ordinary_quiescent":
            if str((quiescence or {}).get("head") or "") != head:
                return None
        upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
        if int(_git(root, "rev-list", "--count", f"{upstream}..HEAD") or "0") != 0:
            return None
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
        "pull": pull,
        "comments": comments,
        "runs": runs,
        "owner": owner,
        "repo": repo,
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
    """Return the non-terminal block for a valid hold whose checks are not yet green.

    Applies to BOTH candidate kinds, and this breadth is the point.

    THE SCAR. Until 2026-08-28 this returned early unless the branch was ``sol/*``.
    An ordinary ``claude/*`` branch carrying a fully ratified hold — draft, disarmed,
    Sol authority and Sol release condition recorded, exact head pushed, worktree
    clean — therefore fell through to the canonical guard for the entire pre-green
    window and was told to "complete commit -> push -> PR -> CI -> squash-merge ->
    render/deploy -> live verification". That instruction is unfollowable by
    construction: DEC:SOL-HOLD-IS-A-MERGE-BARRIER forbids merging the very PR the
    message demands be merged, and the sweeper is barred from it too. Measured on the
    TFG-1 R3 records carrier (PR #6608): 121 consecutive blocks in that state, every
    one advising an action repository law prohibits. A guard that repeats an illegal
    instruction teaches sessions to distrust the guard, which is worse than silence.

    Deliberately NOT a widening of permission. Status ``parked`` is still the only
    terminal exit and still requires every binding check concluded green; the pending
    and red paths below both return ``decision: block``. This changes only WHICH
    correct-shaped block a lawful hold receives, so the session waits or repairs
    instead of being pointed at a forbidden merge. ``_parked_hold`` is untouched.

    The ``sol/*`` case keeps its extra branch-identity warning because renaming a Sol
    authority branch causes GitHub to close/rekey the held PR; ordinary holds get the
    same do-not-mutate guidance without the rename-specific framing.
    """
    kind = probe.get("candidate_kind")
    branch = str(probe.get("branch") or "")
    if kind == "sol_authority":
        if not branch.startswith("sol/"):
            return None
        identity = "Sol authority branch"
    elif kind in {"ordinary_unmerged", "ordinary_latched", "ordinary_quiescent"}:
        if not branch.startswith("claude/"):
            return None
        identity = "held branch"
    else:
        return None

    status = probe.get("status")
    if status == "pending":
        pending = ", ".join(str(name) for name in probe.get("pending", [])[:8]) or "binding checks not yet concluded"
        return {
            "decision": "block",
            "reason": (
                f"HOLD-FOR-SOL WAITING: PR #{probe['number']} is a ratified Sol hold on "
                f"{branch}; exact head {str(probe['head'])[:12]} is pushed and clean, "
                f"but checks are not yet complete ({pending}). Do not rename the branch, "
                "close/reopen the PR, arm merge-on-green, merge, render, or mutate PR identity. "
                "Wait for the existing check watcher only — do not re-poll CI to answer this "
                "block, and do not file SHIP LOOP BLOCKED, because waiting is not a qualifying "
                "blocker. If checks conclude green this state becomes terminal PARKED; if a "
                f"binding check concludes red, repair that check without treating the {identity} "
                "as the blocker."
            ),
        }
    if status == "red":
        red = ", ".join(str(name) for name in probe.get("red", [])[:8]) or "binding check failure"
        return {
            "decision": "block",
            "reason": (
                f"HOLD-FOR-SOL CHECKS RED: PR #{probe['number']} remains held and must not merge. "
                f"Binding checks are red ({red}). Repair the failing check on the same held PR; "
                f"do not rename the {identity}, close/reopen the PR, arm merge-on-green, "
                "or use branch mutation as a ship-loop escape. A new exact head must earn its own "
                "green binding proof before it can become PARKED."
            ),
        }
    return None


def _ledger(
    guard: ModuleType, payload: dict[str, Any]
) -> tuple[Path | None, dict[str, Any] | None]:
    """Return this session's existing guard ledger; never create another store."""
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
    """Use the guard's atomic transaction or lose only the optional latch."""
    if path is None:
        return None
    updater = getattr(guard, "_update_ledger", None)
    if not callable(updater):
        return None
    try:
        return updater(path, mutate)
    except Exception:
        return None


def _clear_wait(
    guard: ModuleType, path: Path | None, state: dict[str, Any] | None
) -> None:
    """Clear only the shared quiescence record, preserving watcher consumption."""
    if (
        path is None
        or not isinstance(state, dict)
        or not isinstance(state.get("ci_quiescence"), dict)
    ):
        return
    clear = getattr(guard, "_ci_quiescence_clear", None)
    if callable(clear):
        try:
            clear(path, state)
            return
        except Exception:
            pass
    _update_ledger(guard, path, lambda latest: latest.pop("ci_quiescence", None))


def _clear_parked_latch(guard: ModuleType, path: Path | None) -> None:
    _update_ledger(guard, path, lambda latest: latest.pop("parked_latch", None))


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
            "ship loop unless Sol releases the hold. This is the one terminal "
            "receipt; identical later observations stay silent."
        )
    }


def _authority_fingerprint(guard: ModuleType, probe: dict[str, Any]) -> str:
    """Bind the wait to PR metadata plus the comments that ratified the hold."""
    extra = [
        {
            "id": comment.get("id"),
            "updated_at": comment.get("updated_at"),
            "body": str(comment.get("body") or ""),
        }
        for comment in probe.get("comments", [])
        if isinstance(comment, dict)
    ]
    return str(guard._ci_authority_fingerprint(probe["pull"], extra=extra))


def _route_material(
    guard: ModuleType,
    path: Path | None,
    state: dict[str, Any] | None,
    quiescence: dict[str, Any],
    probe: dict[str, Any],
    kind: str,
    checks: list[str],
    checks_fingerprint: str,
    authority_fingerprint: str,
) -> bool:
    """Emit/latch one canonical material-event receipt when guard support exists."""
    event_route = getattr(guard, "_ci_event_route", None)
    receipt = getattr(guard, "_ci_material_receipt", None)
    if path is None or not isinstance(state, dict):
        return False
    if not callable(event_route) or not callable(receipt):
        return False
    try:
        route = event_route(
            kind,
            pr=probe["number"],
            head=probe["head"],
            checks=checks,
        )
        return bool(
            receipt(
                path,
                state,
                quiescence,
                route,
                checks_fingerprint=checks_fingerprint,
                authority_fingerprint=authority_fingerprint,
            )
        )
    except Exception:
        return False


def _red_route_kind(guard: ModuleType, probe: dict[str, Any]) -> str:
    """Classify every-red infrastructure/inherited cases; own red stays builder."""
    red_pairs = getattr(guard, "_red_pairs", None)
    infrastructure = getattr(guard, "_ci_infrastructure_red", None)
    if not callable(red_pairs):
        return "builder_red"
    try:
        pairs = list(red_pairs(probe.get("runs", [])))
    except Exception:
        return "builder_red"
    if callable(infrastructure):
        try:
            if infrastructure(pairs):
                return "infrastructure"
        except Exception:
            pass

    # Preserve the existing fail-closed base-side proof. Only `failure` is
    # excludable, and every red must be covered before the product worker routes
    # away. Any unreadable/stale proof keeps ownership with the builder.
    base_probe = getattr(guard, "_base_side_pre_merge", None)
    started_stamp = getattr(guard, "_started_stamp", None)
    non_binding = getattr(guard, "_is_non_binding_check", None)
    if not callable(base_probe) or not callable(started_stamp):
        return "builder_red"
    names = list(
        dict.fromkeys(name for name, conclusion in pairs if conclusion == "failure")
    )
    if not names or any(conclusion != "failure" for _name, conclusion in pairs):
        return "builder_red"
    starts: list[str] = []
    try:
        for run in probe.get("runs", []):
            name = str(run.get("name") or "unnamed check")
            if callable(non_binding) and non_binding(name):
                continue
            if run.get("conclusion") != "failure":
                continue
            stamp = started_stamp(run, "started_at", "completed_at")
            if stamp:
                starts.append(stamp)
        reference = min(starts) if starts else ""
        excused, _unavailable = base_probe(
            probe["owner"],
            probe["repo"],
            probe["head"],
            probe["branch"],
            reference,
            names,
        )
    except Exception:
        return "builder_red"
    return "inherited_main" if all(name in excused for name in names) else "builder_red"


def _handle_stop(guard: ModuleType, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve one Stop; ``None`` delegates byte-for-byte to the canonical guard."""
    path, state = _ledger(guard, payload)

    # The first pending observation has already paid for and recorded all remote
    # truth. Identical later observations consult only local head/dirt and the
    # already-owned watcher process identity. No GitHub probe happens here.
    if path is not None and isinstance(state, dict) and isinstance(
        state.get("ci_quiescence"), dict
    ):
        fast = getattr(guard, "_ci_quiescence_fast_path", None)
        root = guard._repo_root(payload)
        try:
            if callable(fast) and root is not None and fast(Path(root), path, state):
                return {"action": "silent"}
        except Exception:
            # The fast path is optional optimization, never permission.
            pass
        path, state = _ledger(guard, payload)

    latched = str((state or {}).get("parked_latch") or "")
    try:
        probe = _hold_probe(guard, payload)
    except HoldProbeUnanswerable:
        return None
    except Exception:
        return None

    if probe is None:
        # Positive local/remote evidence says the prior state no longer derives.
        # An outage took the exception path above and deliberately clears nothing.
        _clear_wait(guard, path, state)
        _clear_parked_latch(guard, path)
        return None

    quiescence = (state or {}).get("ci_quiescence")

    if probe["status"] == "parked":
        # PARKED itself is the one green wake/release receipt for a hold. Clear
        # the pending wait and atomically write only the narration latch.
        if isinstance(quiescence, dict):
            _clear_wait(guard, path, state)
        key = f"parked:{probe['number']}:{probe['head']}"

        def latch(latest: dict[str, Any]) -> str:
            if str(latest.get("parked_latch") or "") == key:
                return "already"
            latest["parked_latch"] = key
            return "written"

        latch_result = _update_ledger(guard, path, latch)
        if latch_result == "already" or (latch_result is None and latched == key):
            return {"action": "silent"}
        return {"action": "emit", "value": _parked_message(probe)}

    checks_fingerprint = str(guard._ci_checks_fingerprint(probe["runs"]))
    authority_fingerprint = _authority_fingerprint(guard, probe)

    if isinstance(quiescence, dict):
        old_authority = str(quiescence.get("authority_fingerprint") or "")
        if (
            probe["status"] == "pending"
            and old_authority
            and old_authority != authority_fingerprint
            and _route_material(
                guard,
                path,
                state,
                quiescence,
                probe,
                "hold_change",
                probe["pending"],
                checks_fingerprint,
                authority_fingerprint,
            )
        ):
            return {"action": "silent"}

        if probe["status"] == "pending":
            # The only reason an exact wait reaches remote classification again
            # is that its watcher died or became unanswerable. Still-pending CI is
            # missing evidence, centrally routed once; no successor is admitted.
            if _route_material(
                guard,
                path,
                state,
                quiescence,
                probe,
                "missing_evidence",
                probe["pending"],
                checks_fingerprint,
                authority_fingerprint,
            ):
                return {"action": "silent"}
        elif probe["status"] == "red":
            kind = _red_route_kind(guard, probe)
            if kind != "builder_red" and _route_material(
                guard,
                path,
                state,
                quiescence,
                probe,
                kind,
                probe["red"],
                checks_fingerprint,
                authority_fingerprint,
            ):
                return {"action": "silent"}
            # Own red never gets a cheap wait escape.
            _clear_wait(guard, path, state)
    _clear_parked_latch(guard, path)
    if probe["status"] == "pending" and not isinstance(quiescence, dict):
        enter = getattr(guard, "_enter_ci_quiescence", None)
        if callable(enter) and path is not None and isinstance(state, dict):
            try:
                if enter(
                    path,
                    state,
                    branch=probe["branch"],
                    number=probe["number"],
                    head=probe["head"],
                    pending=probe["pending"],
                    passed=probe["passed"],
                    checks_fingerprint=checks_fingerprint,
                    authority_fingerprint=authority_fingerprint,
                    mode="hold",
                ):
                    # The shared helper emits the sole CI_QUIESCENT receipt.
                    return {"action": "silent"}
            except Exception:
                pass

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
