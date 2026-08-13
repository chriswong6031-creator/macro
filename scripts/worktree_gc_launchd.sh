#!/bin/zsh
# Launchd wrapper for the fleet worktree GC (see ops/launchd/*.plist for install).
#
# TRUTH SOURCES, deliberately split:
#   * CONFIG  — extracted from origin/main at run time. The armed flag is an
#     operator-ratified state (config/worktree_gc.json `_armed_ratification`);
#     reading it from main means a stale/dirty primary checkout can neither
#     disarm nor arm the sweep by accident.
#   * SCRIPT  — the primary checkout's scripts/worktree_gc.py. Every deletion
#     gate in the tool is fail-closed (locked, dirty, unpushed, open-PR,
#     live-process, young, outside-roots), so a stale script copy degrades to
#     refusing, never to over-deleting.
set -u
REPO="/Users/chriswong/Documents/Cluade/Macro Dashboard"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "== worktree-gc $STAMP =="
cd "$REPO" || { echo "primary checkout missing"; exit 1; }
git fetch origin main --quiet 2>&1 | tail -1
CFG="$(mktemp -t worktree-gc-config)"
if ! git show origin/main:config/worktree_gc.json > "$CFG" 2>/dev/null; then
  echo "could not read config from origin/main — refusing (fail-closed)"
  exit 1
fi
python3 scripts/worktree_gc.py --apply --repo-root "$REPO" --config "$CFG"
RC=$?
rm -f "$CFG"
echo "== worktree-gc done rc=$RC =="
exit $RC
