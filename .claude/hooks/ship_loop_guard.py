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


def _token_from_env() -> str:
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _get_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "macro-dashboard-ship-loop-guard",
    }
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


def _render_status(owner: str, repo: str, merge_sha: str) -> tuple[str, str]:
    query = urllib.parse.urlencode(
        {"event": "push", "head_sha": merge_sha, "per_page": "20"}
    )
    payload = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/render.yml/runs?{query}"
    )
    runs = payload.get("workflow_runs", [])
    if not runs:
        return "pending", "The required render workflow has not started yet."
    run = max(runs, key=lambda item: item.get("created_at") or "")
    if run.get("status") != "completed":
        return "pending", f"Render workflow is {run.get('status') or 'pending'}."
    if run.get("conclusion") != "success":
        return "failed", f"Render workflow concluded {run.get('conclusion') or 'unknown'}."
    return "success", ""


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

    changed = _run(
        root,
        "git",
        "diff",
        "--name-only",
        str(state.get("start_head")),
        head,
    ).splitlines()
    needs_render = any(
        item.startswith("templates/")
        or (item.startswith("scripts/") and Path(item).name.startswith("build_"))
        for item in changed
    )
    if needs_render:
        try:
            status, detail = _render_status(owner, repo, merge_sha)
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
