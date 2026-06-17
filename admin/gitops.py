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
