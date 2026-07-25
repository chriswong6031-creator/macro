#!/usr/bin/env python3
"""Enforce Macro Dashboard's commit -> PR -> merge -> live completion contract.

SessionStart records a baseline so a shared checkout's pre-existing dirt is never
mistaken for work from this session. Stop blocks when session-created changes are
uncommitted, unpushed, unmerged, still rendering, or not yet present on production.
Repository rules remain the source of truth; this hook makes them executable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


LIVE_HEALTH_URL = "https://mastermind-x.com/api/health"
EXTERNAL_BLOCKERS = {
    "github_unreachable",
    "ci_failed",
    "render_pending",
    "render_failed",
    "live_unreachable",
    "live_stale",
}


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False))


def _run(root: Path, *args: str, timeout: int = 45) -> str:
    proc = subprocess.run(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail[:500]}")
    return proc.stdout.strip()


def _run_raw(root: Path, *args: str, timeout: int = 45) -> str:
    """Run git while preserving porcelain's leading status column."""
    proc = subprocess.run(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail[:500]}")
    return proc.stdout


def _repo_root(payload: dict[str, Any]) -> Path | None:
    candidates = [
        os.environ.get("CLAUDE_PROJECT_DIR"),
        payload.get("cwd"),
        os.getcwd(),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            root = Path(candidate).resolve()
            found = _run(root, "git", "rev-parse", "--show-toplevel")
            return Path(found)
        except Exception:
            continue
    return None


def _state_path(root: Path, payload: dict[str, Any]) -> Path:
    session = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("session_id") or "default"))
    repo_key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    directory = Path(tempfile.gettempdir()) / "macro-claude-ship-sessions" / repo_key
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{session}.json"


def _file_digest(path: Path) -> str:
    try:
        if path.is_file() and not path.is_symlink():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        if path.is_symlink():
            return "symlink:" + os.readlink(path)
    except OSError:
        pass
    return "missing"


def _fingerprint(root: Path) -> dict[str, str]:
    """Return path -> status/content hash for the current dirty set."""
    output = _run_raw(
        root,
        "git",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        timeout=90,
    )
    result: dict[str, str] = {}
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status, display_path = line[:2], line[3:]
        # For rename records, the destination is the content-bearing path.
        path = display_path.rsplit(" -> ", 1)[-1].strip('"')
        result[path] = f"{status}:{_file_digest(root / path)}"
    return result


def _changed_since_baseline(baseline: dict[str, str], now: dict[str, str]) -> list[str]:
    return sorted(path for path in set(baseline) | set(now) if baseline.get(path) != now.get(path))


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save(path: Path, state: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _github_slug(root: Path) -> tuple[str, str]:
    remote = _run(root, "git", "remote", "get-url", "origin")
    match = re.search(r"github\.com[/:]([^/]+)/([^/\s]+?)(?:\.git)?$", remote)
    if not match:
        raise RuntimeError(f"origin is not a GitHub repository: {remote}")
    return match.group(1), match.group(2)


_GH_TOKEN_CACHE: list[str] | None = None


def _token_from_env() -> str:
    """A GitHub token for the API calls below.

    Claude Code hooks inherit NEITHER GH_TOKEN nor GITHUB_TOKEN, so every request used
    to go out anonymous — 60/hr shared across the whole host. A busy session burns that
    in minutes and the guard then dies on `HTTP Error 403: rate limit exceeded`, which
    reads as "github_unreachable" and blocks the Stop hook on work that is already
    merged (2026-07-25: #3534 was MERGED on main while the guard reported 403 on every
    turn). `gh auth token` is the same credential the session already uses
    interactively, and lifts the ceiling to 5000/hr.
    """
    global _GH_TOKEN_CACHE
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    if _GH_TOKEN_CACHE is None:
        # Cached (including the empty result) so a gh-less host pays one failed exec,
        # not one per API call.
        try:
            done = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            _GH_TOKEN_CACHE = [done.stdout.strip() if done.returncode == 0 else ""]
        except (OSError, subprocess.SubprocessError):
            _GH_TOKEN_CACHE = [""]
    return _GH_TOKEN_CACHE[0]


def _get_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-ship-loop-guard",
    }
    # Gate the credential on the HOST, never on the URL prefix: every caller below
    # builds api.github.com URLs today, but a future caller that follows a link out of
    # a payload must not hand the token to another origin.
    if urllib.parse.urlsplit(url).hostname == "api.github.com":
        token = _token_from_env()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def _latest_merged_pr(owner: str, repo: str, branch: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {"state": "closed", "head": f"{owner}:{branch}", "base": "main", "per_page": "20"}
    )
    pulls = _get_json(f"https://api.github.com/repos/{owner}/{repo}/pulls?{query}")
    merged = [pull for pull in pulls if pull.get("merged_at")]
    return max(merged, key=lambda pull: pull.get("merged_at") or "") if merged else None


def _check_ci(owner: str, repo: str, head_sha: str) -> tuple[bool, str]:
    payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/commits/{head_sha}/check-runs?per_page=100"
    )
    runs = payload.get("check_runs", [])
    if not runs:
        return False, "No CI check runs were found for the pull-request head."
    bad: list[str] = []
    pending: list[str] = []
    for run in runs:
        name = str(run.get("name") or "unnamed check")
        lowered = name.lower()
        if "workers builds" in lowered and "macro" in lowered:
            continue
        if run.get("status") != "completed":
            pending.append(name)
        elif run.get("conclusion") not in {"success", "neutral", "skipped"}:
            bad.append(f"{name} ({run.get('conclusion')})")
    if bad:
        return False, "Failing CI: " + ", ".join(bad[:8])
    if pending:
        return False, "CI still running: " + ", ".join(pending[:8])
    return True, ""


def _render_triggering_paths(changed: list[str]) -> bool:
    """True when these paths match render.yml's push trigger filter."""
    return any(
        item.startswith("templates/")
        or (item.startswith("scripts/") and Path(item).name.startswith("build_"))
        for item in changed
    )


def _needs_render(root: Path, merge_sha: str, start_head: str, head: str) -> bool:
    """Whether a push-triggered render must exist for ``merge_sha``.

    Scoped to THIS merge's own diff, not the whole session range.
    ``_render_status`` accepts a successful push render at this merge or a later
    descendant. render.yml's push trigger is path-filtered to templates/** +
    scripts/build_*.py, so this precondition belongs only to a merge that itself
    touched one of those paths.

    start_head..head was the wrong basis on a shared main: this repo runs many
    concurrent sessions, and a session that syncs its worktree to origin/main
    sweeps every OTHER session's merges into that range. One unrelated
    templates/ merge then demanded a render on a merge commit that could never
    have produced one — an unsatisfiable block, not a real gap. (Observed
    2026-07-25: PR #3481 changed only .github/workflows/ci.yml, yet five
    template/builder files from concurrent merges set needs_render.)

    This TIGHTENS alignment rather than loosening the gate: a PR that does touch
    templates/ still needs a successful covering render before it may pass.
    """
    try:
        changed = _run(
            root, "git", "diff", "--name-only", f"{merge_sha}^", merge_sha
        ).splitlines()
    except Exception:
        # Root/orphan merge or unavailable parent — fall back to the session
        # range, which over-requires rather than under-requires a render.
        changed = _run(root, "git", "diff", "--name-only", start_head, head).splitlines()
    return _render_triggering_paths(changed)


def _same_or_descendant(root: Path, merge_sha: str, candidate_sha: str) -> bool:
    """Whether ``candidate_sha`` contains ``merge_sha`` in the local git graph."""
    if candidate_sha == merge_sha:
        return True
    if not candidate_sha:
        return False
    try:
        _run(root, "git", "merge-base", "--is-ancestor", merge_sha, candidate_sha)
    except Exception:
        return False
    return True


def _render_status(root: Path, owner: str, repo: str, merge_sha: str) -> tuple[str, str]:
    """Return the state of a push render that covers ``merge_sha``.

    render.yml deliberately coalesces a merge burst: it keeps one in-flight run,
    supersedes redundant pending runs, and the survivor unions every dirty scope
    since the last covering watermark. Requiring the exact merge's run to succeed
    contradicts that design and caused agents to cancel/re-run healthy shared
    renders merely to clear their own Stop hook. A successful main descendant is
    therefore the correct proof that this merge's render inputs were covered.
    """
    query = urllib.parse.urlencode(
        {"event": "push", "branch": "main", "per_page": "100"}
    )
    payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/render.yml/runs?{query}"
    )
    covering = [
        run
        for run in payload.get("workflow_runs", [])
        if _same_or_descendant(root, merge_sha, str(run.get("head_sha") or ""))
    ]
    if not covering:
        return "pending", "No render covering this merge has started yet."

    covering.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    if any(
        run.get("status") == "completed" and run.get("conclusion") == "success"
        for run in covering
    ):
        return "success", ""

    pending = [run for run in covering if run.get("status") != "completed"]
    if pending:
        state = pending[0].get("status") or "pending"
        return (
            "pending",
            f"A shared render covering this merge is {state}; monitor it without cancelling or re-running it.",
        )

    newest = covering[0]
    return (
        "failed",
        "Covering render concluded "
        f"{newest.get('conclusion') or 'unknown'}; diagnose the cause before one controlled retry.",
    )


def _find_commit(value: Any) -> str:
    """Find a plausible deployed git SHA in a health payload."""
    preferred = {"commit", "commit_sha", "git_sha", "git_commit", "revision", "sha"}
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in preferred and isinstance(child, str):
                match = re.search(r"\b[0-9a-f]{7,40}\b", child, re.I)
                if match:
                    return match.group(0)
        for child in value.values():
            found = _find_commit(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_commit(child)
            if found:
                return found
    return ""


def _block(
    path: Path,
    state: dict[str, Any],
    payload: dict[str, Any],
    code: str,
    reason: str,
) -> None:
    """Block Stop, except after a repeated and explicitly reported external blocker."""
    previous = state.get("last_blocker")
    count = int(state.get("blocker_count") or 0) + 1 if previous == code else 1
    state["last_blocker"] = code
    state["blocker_count"] = count
    _save(path, state)
    final = str(payload.get("last_assistant_message") or "").lstrip()
    if (
        code in EXTERNAL_BLOCKERS
        and payload.get("stop_hook_active")
        and count >= 2
        and final.startswith("SHIP LOOP BLOCKED:")
    ):
        return
    _emit(
        {
            "decision": "block",
            "reason": (
                f"SHIP LOOP {code}: {reason}\n"
                "Continue the task and complete commit → push → PR → CI → squash-merge → "
                "render/deploy → live verification. If the same genuine external blocker "
                "persists after another attempt, finish with `SHIP LOOP BLOCKED:` and the "
                "specific evidence."
            ),
        }
    )


def _session_start(root: Path, path: Path, payload: dict[str, Any]) -> None:
    source = str(payload.get("source") or "")
    state = _load(path)
    if state is None or source in {"startup", "clear"}:
        state = {
            "root": str(root),
            "start_head": _run(root, "git", "rev-parse", "HEAD"),
            "baseline": _fingerprint(root),
            "last_blocker": "",
            "blocker_count": 0,
        }
        _save(path, state)
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "MANDATORY SHIP LOOP: Repository rules grant standing approval for "
                    "commit, push, pull request, CI repair, same-day squash merge, deploy "
                    "waiting, and real-live verification. Work only in a fresh "
                    ".claude/worktrees/ claude/* branch. Do not stop at a local change, "
                    "commit, or open PR. This session's starting dirty files were recorded "
                    "and are excluded from enforcement."
                ),
            }
        }
    )


def _stop(root: Path, path: Path, payload: dict[str, Any]) -> None:
    state = _load(path)
    # Hooks can be installed during an already-running session. Fail open once so
    # that pre-hook work is not misclassified; every later session is enforced.
    if state is None:
        return

    baseline = state.get("baseline") or {}
    dirty = _changed_since_baseline(baseline, _fingerprint(root))
    if dirty:
        preview = ", ".join(dirty[:12])
        _block(path, state, payload, "uncommitted", f"Session-created changes remain: {preview}")
        return

    head = _run(root, "git", "rev-parse", "HEAD")
    if head == state.get("start_head"):
        return

    branch = _run(root, "git", "branch", "--show-current")
    if not branch or branch in {"main", "master"}:
        _block(path, state, payload, "unsafe_branch", f"Work is on {branch or 'detached HEAD'}.")
        return

    try:
        upstream = _run(root, "git", "rev-parse", "--abbrev-ref", "@{upstream}")
    except RuntimeError:
        _block(path, state, payload, "unpushed", f"{branch} has no upstream branch.")
        return
    ahead = int(_run(root, "git", "rev-list", "--count", f"{upstream}..HEAD") or "0")
    if ahead:
        _block(path, state, payload, "unpushed", f"{ahead} commit(s) have not been pushed.")
        return

    try:
        owner, repo = _github_slug(root)
        pull = _latest_merged_pr(owner, repo, branch)
    except Exception as exc:
        _block(path, state, payload, "github_unreachable", str(exc))
        return
    if not pull:
        _block(path, state, payload, "unmerged", f"No merged main pull request found for {branch}.")
        return

    head_sha = str((pull.get("head") or {}).get("sha") or head)
    try:
        ci_ok, ci_reason = _check_ci(owner, repo, head_sha)
    except Exception as exc:
        _block(path, state, payload, "github_unreachable", str(exc))
        return
    if not ci_ok:
        code = "ci_failed" if ci_reason.startswith("Failing") else "render_pending"
        _block(path, state, payload, code, ci_reason)
        return

    merge_sha = str(pull.get("merge_commit_sha") or "")
    try:
        _run(root, "git", "fetch", "origin", "main", timeout=90)
        _run(root, "git", "merge-base", "--is-ancestor", merge_sha, "origin/main")
    except Exception as exc:
        _block(path, state, payload, "github_unreachable", f"Merge is not confirmed on origin/main: {exc}")
        return

    needs_render = _needs_render(root, merge_sha, str(state.get("start_head")), head)
    if needs_render:
        try:
            status, detail = _render_status(root, owner, repo, merge_sha)
        except Exception as exc:
            _block(path, state, payload, "github_unreachable", str(exc))
            return
        if status != "success":
            _block(
                path,
                state,
                payload,
                "render_failed" if status == "failed" else "render_pending",
                detail,
            )
            return

    try:
        deployed = _find_commit(_get_json(LIVE_HEALTH_URL))
        if not deployed:
            raise RuntimeError("Production health response did not include a git commit.")
        deployed_full = _run(root, "git", "rev-parse", deployed)
        _run(root, "git", "merge-base", "--is-ancestor", merge_sha, deployed_full)
    except Exception as exc:
        _block(path, state, payload, "live_stale", f"Production does not yet contain the merge: {exc}")
        return

    try:
        path.unlink()
    except OSError:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    root = _repo_root(payload)
    if root is None:
        return
    path = _state_path(root, payload)
    event = str(payload.get("hook_event_name") or "")
    try:
        if event == "SessionStart":
            _session_start(root, path, payload)
        elif event == "Stop":
            _stop(root, path, payload)
    except Exception as exc:
        # A broken enforcement hook must be visible, but must not brick Claude.
        if event == "Stop":
            _emit(
                {
                    "decision": "block",
                    "reason": (
                        "SHIP LOOP guard_error: The completion guard failed unexpectedly: "
                        f"{exc}. Repair `.claude/hooks/ship_loop_guard.py` before stopping."
                    ),
                }
            )


if __name__ == "__main__":
    main()
