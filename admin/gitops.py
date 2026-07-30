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
# The three outbox ledgers are the Intelligence Desk approve path: the Actions
# publisher reads the GIT-TRACKED outbox from main, so an item queued only into
# the VPS checkout is an item that never posts. All three carry merge=union in
# .gitattributes (append-only, id-first fold), so a concurrent-append rebase
# resolves itself — which is what makes the retry loop below safe.
_ALLOWED_PATHS = frozenset({
    "config.yml",
    "data/marketing/account_overrides.json",
    "data/marketing/outbox/items.jsonl",
    "data/marketing/outbox/status_ledger.jsonl",
    "data/marketing/outbox/activity.jsonl",
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


def _checked_paths(paths) -> tuple[list[str], dict | None]:
    """Normalise a paths argument and enforce the allowlist.

    Returns ``(paths, refusal)``. A non-None ``refusal`` is the caller's return
    value verbatim — the allowlist is the one thing that must read identically
    for every commit entry point, so it lives here rather than in each of them.
    """
    if isinstance(paths, str):
        paths = [paths]
    paths = [str(p).replace("\\", "/") for p in (paths or [])]
    if not paths:
        return [], {"ok": False, "error": "no paths given"}
    bad = [p for p in paths if p not in _ALLOWED_PATHS]
    if bad:
        return [], {"ok": False, "error": f"refused: paths not allowlisted: {bad}"}
    return paths, None


def _commit_scoped(paths: list[str], message: str) -> tuple[dict | None, list[str]]:
    """git add + a commit SCOPED to ``paths``. Shared by both commit_paths*.

    Returns ``(early, log)``. A non-None ``early`` is the caller's return value
    verbatim: either the clean-tree no-op (committed:False) or an add/commit
    failure. ``None`` means the commit landed and the caller owns what happens
    next (push, or push-with-retry).
    """
    log: list[str] = []
    # Which of the requested paths actually have changes (staged or unstaged)?
    dirty = []
    for p in paths:
        rc, out, _ = _git("status", "--porcelain", "--", p)
        if rc == 0 and out.strip():
            dirty.append(p)
    if not dirty:
        # Nothing changed on disk — the override matched the committed content.
        return {"ok": True, "committed": False, "pushed": False,
                "warning": "no changes to commit for the given paths", "log": log}, log

    rc, out, err = _git("add", "--", *dirty)
    log.append(f"git add: {err or out or 'ok'}")
    if rc != 0:
        return {"ok": False, "error": err or "git add failed", "log": log}, log
    # Scope the commit to exactly these paths so a pre-staged unrelated file can't
    # ride along into the commit (and the live-main push).
    rc, out, err = _git("commit", "-m", message, "--", *dirty)
    log.append(f"git commit: {(out or err)[:300]}")
    if rc != 0:
        return {"ok": False, "error": err or "git commit failed", "log": log}, log
    return None, log


def commit_paths(paths, message: str = "admin: update", push: bool = False,
                 confirm: bool = False) -> dict:
    """Commit (and optionally push) an ALLOWLISTED set of repo-relative paths.

    Generalises commit(): the same confirm gate, the same push-only-on-a-main-
    tracking-branch safety, but scoped to the given files instead of just
    config.yml. Any path outside _ALLOWED_PATHS is refused outright. If a path
    has no staged/working changes it is skipped (not an error) — a no-op toggle
    that re-writes the same content still succeeds with committed:False.

    ONE push, no retry: a push refused because origin moved strands the commit
    locally. Callers whose write must actually reach main want
    ``commit_paths_synced`` instead.

    Returns the same shape as commit(): {ok, committed?, pushed?, warning?/error?, log}.
    """
    if not confirm:
        return {"ok": False, "error": "confirm required for git commit/push"}
    paths, refusal = _checked_paths(paths)
    if refusal is not None:
        return refusal

    early, log = _commit_scoped(paths, message)
    if early is not None:
        return early

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


def commit_paths_synced(paths, message: str = "admin: update", *,
                        confirm: bool = False, attempts: int = 3) -> dict:
    """commit_paths() for a write that must actually REACH main, with retry.

    Same allowlist, same confirm gate, same scoped commit, same never-push-off-a-
    main-tracking-branch guard. What differs is the push: ``commit_paths`` fires
    ONE ``git push`` and a refusal strands the commit on this disk forever. On the
    deployed VPS that is a routine outcome, not an edge case — the press wire
    commits every few minutes, so origin has usually moved between the read and
    the push, and a stranded outbox row is a post the publisher never sees.

    So: on a refused push, ``git fetch`` then ``git rebase`` onto the upstream and
    try again, up to ``attempts`` pushes. This is only safe because the callers'
    files are append-only ledgers carrying merge=union in .gitattributes — the
    driver resolves a concurrent-append collision by keeping both sides, and the
    readers fold id-first so a duplicated row is inert. Never ``push -f``, never
    ``reset``: this function may lose no one else's commit.

    Two honest non-delivery outcomes:
      * attempts exhausted -> {ok: True, committed: True, pushed: False, warning}.
        The commit is real, so this is not an error — but it is not delivery
        either, and on the deployed VPS it is not durable: that checkout pulls
        with ``git reset --hard FETCH_HEAD`` (app/deploy/update.sh) every few
        minutes, which discards an unpushed commit. The warning says only what is
        true: committed here, not on main.
      * the rebase itself conflicts -> ``git rebase --abort`` (never leave the
        checkout mid-rebase) and {ok: False, committed: True, pushed: False,
        error}. Something is wrong that a retry cannot fix; say so.

    Returns {ok, committed?, pushed?, attempts?, warning?/error?, log}.
    """
    if not confirm:
        return {"ok": False, "error": "confirm required for git commit/push"}
    paths, refusal = _checked_paths(paths)
    if refusal is not None:
        return refusal
    try:
        attempts = max(1, int(attempts))
    except (TypeError, ValueError):
        attempts = 1

    early, log = _commit_scoped(paths, message)
    if early is not None:
        return early

    st = status()
    if not st["can_push_live"]:
        # Dev checkouts never push. The commit is local and that is the whole
        # intended behaviour here, so this is ok:True with an honest warning.
        return {"ok": True, "committed": True, "pushed": False,
                "warning": "committed locally; refused to push (not on a main tracking branch)",
                "log": log}
    upstream = st["upstream"]

    last = ""
    made = 0          # pushes actually ATTEMPTED, which is not always `attempts`
    for n in range(1, attempts + 1):
        rc, out, err = _git("push", timeout=90)
        log.append(f"git push ({n}/{attempts}): {(out or err)[:300]}")
        if rc == 0:
            return {"ok": True, "committed": True, "pushed": True,
                    "attempts": n, "log": log}
        made = n
        last = f"the push was refused ({err or out or 'no detail'})"
        if n == attempts:
            break
        # Refused. The overwhelmingly likely cause is that origin moved under us,
        # so catch up and retry rather than treating a moving target as an error.
        rc, out, err = _git("fetch", timeout=90)
        log.append(f"git fetch: {(err or out or 'ok')[:200]}")
        if rc != 0:
            # Name the step that actually failed. Reporting this as "push did not
            # land in N attempts" would blame the wrong command AND claim retries
            # that never happened — the operator would go looking at the remote's
            # ref state instead of at whether this box can reach it at all.
            last = (f"git fetch failed ({err or out or 'no detail'}), so there "
                    "was nothing new to rebase onto and retrying the push would "
                    "have been refused the same way")
            break
        rc, out, err = _git("rebase", upstream, timeout=90)
        log.append(f"git rebase {upstream}: {(out or err)[:300]}")
        if rc != 0:
            # TWO different failures land here and they need different words. A
            # rebase that CONFLICTED started, so the abort unwinds it. A rebase
            # git REFUSED never started at all — a dirty working tree does it,
            # which is the normal state of the VPS checkout between lanes — and
            # then the abort fails too, because there is nothing to abort. Calling
            # that second case "conflicted" sends the operator hunting for a merge
            # conflict that never existed.
            arc, aout, aerr = _git("rebase", "--abort", timeout=60)
            log.append(f"git rebase --abort: {(aerr or aout or 'ok')[:200]}")
            detail = err or out or "no detail"
            if arc == 0:
                why = (f"the rebase onto {upstream} conflicted ({detail}) and was "
                       "aborted, so this checkout is back as it was")
            else:
                why = (f"the rebase onto {upstream} failed ({detail}) and the abort "
                       f"did not succeed either ({aerr or aout or 'no detail'}) — "
                       "usually that means the rebase never started, but CHECK "
                       "this checkout before trusting it")
            return {
                "ok": False, "committed": True, "pushed": False, "attempts": n,
                "error": f"committed locally; {why}",
                "log": log,
            }

    # WORDING IS LOAD-BEARING. Do not promise here that the commit "rides the
    # next sync": on the deployed VPS it does not. app/deploy/update.sh pulls with
    # `git reset --hard FETCH_HEAD` every ~3 minutes whenever origin/main moved,
    # which DISCARDS an unpushed local commit and reverts the tracked files it
    # touched. Whether this commit survives depends on the checkout, so state what
    # is known — it exists here, it is not on main — and let the caller decide
    # what to tell the operator.
    return {"ok": True, "committed": True, "pushed": False, "attempts": made,
            "warning": (f"committed locally; not pushed after {made} push "
                        f"attempt(s) — {last}. The commit exists on this checkout "
                        "but is NOT on main."),
            "log": log}
