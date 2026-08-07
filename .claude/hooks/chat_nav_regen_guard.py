#!/usr/bin/env python3
"""PostToolUse guard: regenerate chat.html's header on a nav-source edit.

House law (CLAUDE.md §Navigation source-of-truth + §Ops): templates/chat.html is
a PLAIN-COPY page — check_template_site_sync requires it to byte-match
site/chat.html, so Jinja cannot run there and it cannot ``{% include %}`` the
shared header the other 113 product templates use.  Its header is therefore
GENERATED from templates/_site_nav.html.j2 by scripts/sync_chat_nav.py, and the
regenerated pair must land in the SAME PR as the partial edit.

Lanes keep forgetting the regen — nav drift has reddened main three times
(#4637, #4666, #4721) — and the CI copy that catches it lives in ci-pack, which
takes ~2h: #4666's ci run started 03:43:06Z and the PR squash-merged 8m30s
later, so the red arrived on main rather than on the PR.  (The fast always-on
copy in .github/workflows/fences.yml now closes that window from the CI side;
this hook closes it one step earlier, in the editing session's own tree.)

Two commands, in order, because they cover different halves:
  * ``sync_chat_nav.py --fix``  re-splices the header from the partial — and
    carries the optimizer's ``?v=``/``defer`` decorations across the splice, so
    running it can never strip the `immutable, max-age=1y` stamps off a page
    with no render lane to re-stamp them;
  * ``check_template_site_sync.py --fix``  re-syncs templates/ -> site/, which
    sync_chat_nav does NOT do when the edit was to chat.html's BODY (no header
    drift => no write => a diverged pair that reddens every open PR).

Fail OPEN on anything ambiguous or on internal error — a hook that bricks
editing is worse than a missed regen (the CI guards still catch those).
Exit 2 (feedback to the model) only when a fixer reports a state ``--fix``
cannot heal: a lost/duplicated ``<nav class="site-nav">`` boundary, a dropped
data-base shim, or a wrong-direction pair where templates/ is the stale side.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Editing any of these can leave templates/chat.html's generated header — or its
# site/ twin — stale.  The two partials are the header's SOURCE; chat.html is the
# page whose site copy must keep byte-matching it.
TRIGGERS = {
    "_navlinks.html.j2",
    "_site_nav.html.j2",
    "chat.html",
}

# (script, argv-tail, what a nonzero exit means for the model)
FIXERS = (
    (
        "sync_chat_nav.py",
        ["--fix"],
        "re-splicing templates/chat.html's header from _site_nav.html.j2 failed. "
        "That is a state --fix cannot heal: usually the page's "
        '<nav class="site-nav">…</nav> wrapper was renamed, removed or '
        "duplicated (the splice is keyed on that element), or the splice would "
        "have dropped the data-base shim.",
    ),
    (
        "check_template_site_sync.py",
        ["--fix"],
        "re-syncing the templates/ -> site/ plain-copy pairs failed. --fix heals "
        "in ONE direction and REFUSES when templates/ is the stale side (its ?v= "
        "stamps disagree with the files on disk while site/'s are current) — "
        "copying then would ship bytes the edge caches `immutable, max-age=1y`. "
        "Heal the named template FROM its site/ copy, then re-run.",
    ),
)


def allow():
    sys.exit(0)


def _read(path: Path):
    try:
        return path.read_bytes()
    except OSError:
        return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        allow()
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        allow()
    fp = ti.get("file_path")
    if not fp:
        allow()

    try:
        path = Path(fp)
        if not path.is_absolute():
            path = Path(payload.get("cwd") or os.getcwd()) / path
        path = path.resolve()
    except Exception:
        allow()

    if path.name not in TRIGGERS or path.parent.name != "templates":
        allow()

    repo_root = path.parent.parent
    scripts = repo_root / "scripts"
    if not all((scripts / name).exists() for name, _, _ in FIXERS):
        allow()  # not this repo's layout — nothing to regen

    # The pair is what ships; watch both halves so the report names what moved.
    watched = (Path("templates") / "chat.html", Path("site") / "chat.html")
    before = {w: _read(repo_root / w) for w in watched}
    # check_template_site_sync --fix has no pair filter — it sweeps all ~84
    # plain-copy pairs. Healing a co-diverged sibling is the right outcome (the
    # byte-match law is repo-wide), but it must not be SILENT: an unreported
    # write is a file the session commits without knowing why it changed. So
    # collect what the fixers say they wrote, not just what happened to chat.html.
    announced: list[str] = []

    for name, args, diagnosis in FIXERS:
        try:
            proc = subprocess.run(
                [sys.executable, str(scripts / name), *args],
                cwd=str(repo_root), capture_output=True, text=True, timeout=60,
            )
        except Exception:
            allow()
        if proc.returncode != 0:
            tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-2000:]
            print(
                f"chat_nav_regen_guard: {diagnosis}\n\n"
                f"templates/chat.html's header is GENERATED — do not hand-edit "
                f"it; fix the cause, then run:\n"
                f"  python3 scripts/{name} {' '.join(args)}\n"
                f"and commit the regenerated pair in the same PR (fences.yml "
                f"reds every PR whose chat.html header disagrees with "
                f"_site_nav.html.j2).\n--- {name} output ---\n{tail}",
                file=sys.stderr,
            )
            sys.exit(2)
        for line in (proc.stdout or "").splitlines():
            if line.startswith("FIXED: "):
                announced.append(line[len("FIXED: "):].split(" ", 1)[0])

    # Union: the byte-watch catches a write no fixer announced, the announcements
    # catch a write outside the pair this hook was watching.
    changed = sorted(
        {str(w) for w in watched if _read(repo_root / w) != before[w]}
        | set(announced)
    )
    if changed:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "chat_nav_regen_guard: regenerated " + ", ".join(changed)
                    + f" from your templates/{path.name} edit (house law: "
                    "chat.html cannot {% include %} the shared header, so it is "
                    "generated from _site_nav.html.j2 and its site/ copy must "
                    "byte-match; the regen lands in the same PR as the edit). "
                    "The optimizer's ?v= stamps and defer attributes were "
                    "carried across the splice. Commit these regenerated files "
                    "together with your edit."
                ),
            }
        }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail open
