"""Minimal, guarded git helpers so the admin can land config.yml edits on the repo.

Toggles/interval edits modify the WORKING-TREE config.yml immediately; they only reach
the live build once committed to main. These helpers report git state and (on explicit
confirmation) commit + optionally push config.yml. Outward/irreversible actions (push)
require confirm=True and are surfaced in the UI with a confirmation prompt.
"""
from __future__ import annotations

import subprocess

from .paths import ROOT

_FILE = "config.yml"

# Only these repo-relative paths may be committed+pushed by the admin. Anything
# outside this set is refused — an admin-initiated push can never carry an
# arbitrary file to main. config.yml is the flag/interval store; the marketing
# override file is the operator's desk on/off switch (admin/marketing.py owns it).
_ALLOWED_PATHS = frozenset({
    "config.yml",
    "data/marketing/account_overrides.json",
})


def _git(*args, timeout: int = 20) -> tuple[int, str, str]:
    p = subprocess.run(["git", *args], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def status() -> dict:
    branch = upstream = None
    config_dirty = False
    ahead = behind = 0
    try:
        _, branch, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
        rc, up, _ = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        upstream = up if rc == 0 else None
        rc, out, _ = _git("status", "--porcelain", "--", _FILE)
        config_dirty = bool(out.strip())
        if upstream:
            rc, counts, _ = _git("rev-list", "--left-right", "--count", f"{upstream}...HEAD")
            if rc == 0 and "\t" in counts:
                b, a = counts.split("\t")
                behind, ahead = int(b), int(a)
    except Exception:  # noqa: BLE001
        pass
    on_main = branch in ("main", "master")
    return {
        "branch": branch, "upstream": upstream,
        "config_dirty": config_dirty,
        "ahead": ahead, "behind": behind,
        "on_main": on_main,
        # enable push-to-live ONLY when we're ON a main branch AND it tracks
        # origin/main(or master). commit() does a bare `git push`, so BOTH must hold:
        # the local branch name (else a feature branch tracking origin/main would show
        # the button) AND the upstream target (else a branch named "main" tracking a
        # non-live remote would). Requiring both is strictly safest.
        "can_push_live": bool(on_main and upstream in ("origin/main", "origin/master")),
    }


def commit(message: str = "admin: config update", push: bool = False,
           confirm: bool = False) -> dict:
    if not confirm:
        return {"ok": False, "error": "confirm required for git commit/push"}
    st = status()
    if not st["config_dirty"]:
        return {"ok": False, "error": "config.yml has no uncommitted changes"}
    log = []
    rc, out, err = _git("add", "--", _FILE)
    log.append(f"git add: {err or out or 'ok'}")
    if rc != 0:
        return {"ok": False, "error": err or "git add failed", "log": log}
    # scope the commit to config.yml so a pre-staged unrelated file can't ride along
    # into this commit (and into the live-main push)
    rc, out, err = _git("commit", "-m", message, "--", _FILE)
    log.append(f"git commit: {(out or err)[:300]}")
    if rc != 0:
        return {"ok": False, "error": err or "git commit failed", "log": log}
    if push:
        if not st["can_push_live"]:
            return {"ok": True, "committed": True, "pushed": False,
                    "warning": "committed locally; refused to push (not on a main tracking branch)",
                    "log": log}
        rc, out, err = _git("push", timeout=60)
        log.append(f"git push: {(out or err)[:300]}")
        if rc != 0:
            return {"ok": False, "committed": True, "pushed": False,
                    "error": err or "git push failed", "log": log}
        return {"ok": True, "committed": True, "pushed": True, "log": log}
    return {"ok": True, "committed": True, "pushed": False, "log": log}


def commit_paths(paths, message: str = "admin: update", push: bool = False,
                 confirm: bool = False) -> dict:
    """Commit (and optionally push) an ALLOWLISTED set of repo-relative paths.

    Generalises commit(): the same confirm gate, the same push-only-on-a-main-
    tracking-branch safety, but scoped to the given files instead of just
    config.yml. Any path outside _ALLOWED_PATHS is refused outright. If a path
    has no staged/working changes it is skipped (not an error) — a no-op toggle
    that re-writes the same content still succeeds with committed:False.

    Returns the same shape as commit(): {ok, committed?, pushed?, warning?/error?, log}.
    """
    if not confirm:
        return {"ok": False, "error": "confirm required for git commit/push"}
    if isinstance(paths, str):
        paths = [paths]
    paths = [str(p).replace("\\", "/") for p in (paths or [])]
    if not paths:
        return {"ok": False, "error": "no paths given"}
    bad = [p for p in paths if p not in _ALLOWED_PATHS]
    if bad:
        return {"ok": False, "error": f"refused: paths not allowlisted: {bad}"}

    log = []
    # Which of the requested paths actually have changes (staged or unstaged)?
    dirty = []
    for p in paths:
        rc, out, _ = _git("status", "--porcelain", "--", p)
        if rc == 0 and out.strip():
            dirty.append(p)
    if not dirty:
        # Nothing changed on disk — the override matched the committed content.
        return {"ok": True, "committed": False, "pushed": False,
                "warning": "no changes to commit for the given paths", "log": log}

    rc, out, err = _git("add", "--", *dirty)
    log.append(f"git add: {err or out or 'ok'}")
    if rc != 0:
        return {"ok": False, "error": err or "git add failed", "log": log}
    # Scope the commit to exactly these paths so a pre-staged unrelated file can't
    # ride along into the commit (and the live-main push).
    rc, out, err = _git("commit", "-m", message, "--", *dirty)
    log.append(f"git commit: {(out or err)[:300]}")
    if rc != 0:
        return {"ok": False, "error": err or "git commit failed", "log": log}

    st = status()
    if push:
        if not st["can_push_live"]:
            return {"ok": True, "committed": True, "pushed": False,
                    "warning": "committed locally; refused to push (not on a main tracking branch)",
                    "log": log}
        rc, out, err = _git("push", timeout=60)
        log.append(f"git push: {(out or err)[:300]}")
        if rc != 0:
            return {"ok": False, "committed": True, "pushed": False,
                    "error": err or "git push failed", "log": log}
        return {"ok": True, "committed": True, "pushed": True, "log": log}
    return {"ok": True, "committed": True, "pushed": False, "log": log}
