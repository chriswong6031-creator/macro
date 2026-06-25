"""Audit for STRANDED work — finished changes that never reached the live site
because the manual commit/merge step was forgotten.

Two failure modes it surfaces, both relative to the deployed branch (origin/main):

  1. UNCOMMITTED — a worktree has real changes that were never committed.
  2. UNMERGED   — a branch has committed content that is genuinely NOT on main.

It deliberately ignores the repo's hundreds of "X commits ahead" SQUASH-GHOSTS:
because main is squash-merged, a merged branch keeps its original SHAs and reads
"ahead" forever. The real test is whether merging the branch into main would add
anything (git merge-tree) — only branches that add real, non-conflicting content
are reported as UNMERGED. Branches that merely conflict/diverge (almost always
stale or superseded) are hidden unless you pass --all.

Usage:
  python -m scripts.audit_stranded_work            # recent stranded work
  python -m scripts.audit_stranded_work --all      # include stale/diverged too
  python -m scripts.audit_stranded_work --days 60  # widen the recency window
  python -m scripts.audit_stranded_work --no-fetch # skip the origin/main refresh
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def git(*args: str, cwd: Path | str = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def worktree_branches() -> dict[str, str]:
    """branch short-name -> worktree path (only worktrees that have a branch checked out)."""
    out, path, mp = git("worktree", "list", "--porcelain").stdout, None, {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line.startswith("branch refs/heads/"):
            mp[line[len("branch refs/heads/"):]] = path
        elif not line:
            path = None
    return mp


def is_generated(p: str) -> bool:
    """Build output the engine rewrites every run — NOT forgotten hand-work.

    data/ is all caches/artifacts. Under site/, the page HTML and every
    per-market subdir (stockdata/ohlc/…) are generated, but the top-level
    hand-maintained assets (live.js, theme.js, *.css) are real source.
    """
    if p.startswith("data/"):
        return True
    if p.startswith("site/"):
        rest = p[len("site/"):]
        return "/" in rest or rest.endswith(".html")
    return False


def dirty_source_paths(wt: str) -> list[str]:
    """Changed/untracked SOURCE paths in a worktree (generated output filtered out)."""
    res = git("status", "--porcelain", cwd=wt)
    paths = []
    for line in res.stdout.splitlines():
        if not line:
            continue
        name = line[3:]
        if " -> " in name:           # rename: take the destination
            name = name.split(" -> ", 1)[1]
        name = name.strip().strip('"')
        if not is_generated(name):
            paths.append(name)
    return paths


def newest_mtime(wt: str, paths: list[str]) -> float | None:
    newest = None
    for p in paths:
        fp = os.path.join(wt, p)
        try:
            m = os.path.getmtime(fp)
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return newest


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit stranded (uncommitted / unmerged) work vs origin/main.")
    ap.add_argument("--all", action="store_true", help="also list branches that conflict/diverge from main (likely stale)")
    ap.add_argument("--days", type=int, default=45, help="recency window for UNMERGED branches (default 45)")
    ap.add_argument("--no-fetch", action="store_true", help="skip refreshing origin/main")
    args = ap.parse_args()

    if not args.no_fetch:
        git("fetch", "origin", "main")

    main_sha = git("rev-parse", "--short", "origin/main").stdout.strip()
    main_tree = git("rev-parse", "origin/main^{tree}").stdout.strip()
    now = time.time()
    cutoff = now - args.days * 86400

    # ---- 1. UNCOMMITTED: worktrees with real SOURCE changes never committed ----
    uncommitted = []  # (branch, n_files, age_str, sort_mtime, path)
    for br, wt in sorted(worktree_branches().items()):
        paths = dirty_source_paths(wt)
        if not paths:
            continue
        m = newest_mtime(wt, paths)
        a = age(now - m) if m else "?"
        uncommitted.append((br, len(paths), a, m or 0, wt))
    uncommitted.sort(key=lambda r: r[3], reverse=True)

    # ---- 2. UNMERGED: branches with REAL committed content not on main ----
    unmerged, diverged = [], []  # (branch, age_str, behind, subj, sort_ts)
    for br in git("for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout.split():
        if br == "main":
            continue
        if git("merge-base", "--is-ancestor", br, "origin/main").returncode == 0:
            continue  # fully contained in main — nothing to merge
        mt = git("merge-tree", "--write-tree", "origin/main", br)
        if mt.returncode == 0 and mt.stdout.strip() == main_tree:
            continue  # squash-ghost — adds nothing
        ts = int(git("log", "-1", "--format=%ct", br).stdout.strip() or 0)
        subj = git("log", "-1", "--format=%s", br).stdout.strip()[:58]
        behind = git("rev-list", "--count", f"{br}..origin/main").stdout.strip()
        row = (br, age(now - ts), behind, subj, ts)
        if mt.returncode == 0:
            unmerged.append(row)      # clean real delta — genuinely unmerged
        else:
            diverged.append(row)      # conflicts with main — usually stale/superseded
    unmerged.sort(key=lambda r: r[4], reverse=True)
    diverged.sort(key=lambda r: r[4], reverse=True)

    recent_unmerged = [r for r in unmerged if r[4] >= cutoff]
    old_unmerged = [r for r in unmerged if r[4] < cutoff]

    # ---- report ----
    print(f"STRANDED WORK AUDIT  ·  vs origin/main @ {main_sha}\n")

    if uncommitted:
        cap = len(uncommitted) if args.all else 12
        print(f"⚠  UNCOMMITTED — source changes never committed ({len(uncommitted)}, newest first):")
        for br, n, a, _, wt in uncommitted[:cap]:
            print(f"   {br:<42} {n:>3} src · {a:>4} old · {os.path.basename(wt.rstrip('/'))}")
        if len(uncommitted) > cap:
            print(f"   … +{len(uncommitted) - cap} older (--all to show)")
        print()
    else:
        print("✓  UNCOMMITTED — none\n")

    shown = recent_unmerged + (old_unmerged if args.all else [])
    if shown:
        label = f"({len(shown)})" if args.all else f"({len(recent_unmerged)} in last {args.days}d)"
        print(f"⚠  UNMERGED — committed, real content not on main {label}:")
        for br, a, behind, subj, _ in shown:
            print(f"   {br:<44} {a:>4} old · {behind:>4} behind  ·  {subj}")
        print()
    else:
        print("✓  UNMERGED — none with recent real content\n")

    extra = []
    if not args.all and old_unmerged:
        extra.append(f"{len(old_unmerged)} older unmerged (>{args.days}d)")
    if not args.all and diverged:
        extra.append(f"{len(diverged)} diverged/conflicting (likely stale)")
    if extra:
        print(f"… hidden: {', '.join(extra)}.  Run with --all to show.")

    if not uncommitted and not recent_unmerged:
        print("Nothing actionable is stranded. 🎉")
    return 0


if __name__ == "__main__":
    sys.exit(main())
