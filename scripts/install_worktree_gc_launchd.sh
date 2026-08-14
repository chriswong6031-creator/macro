#!/bin/bash
# Install the per-host worktree GC launchd agent (operator-run, post-ratification).
#
# Usage: bash scripts/install_worktree_gc_launchd.sh [/path/to/primary/checkout]
#
# Installs ~/Library/LaunchAgents/com.macro.worktree-gc.plist running
# scripts/worktree_gc.py --apply daily at 05:17 local.  While
# config/worktree_gc.json carries armed:false the run self-gates to a
# report-only pass (exit 2), so this is safe to install pre-ratification —
# but per the ratification protocol in research/WORKTREE_GC_POLICY.md,
# installation itself is an operator act: sessions must not run this
# unprompted.
set -euo pipefail

# REPO_ROOT = the SWEEP TARGET (git vantage: where fleet worktrees are registered).
# Source files come from THIS installer's own checkout (SRC_DIR) — the primary is
# routinely parked on a commit that predates the tool (verified 2026-08-13: the
# primary HEAD had no scripts/worktree_gc.py at all), so it can never be the
# source of code. It only has to be a git repo; policy+tool are re-extracted from
# origin/main at every run by the wrapper.
REPO_ROOT="${1:-/Users/chriswong/Documents/Cluade/Macro Dashboard}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SRC_DIR/worktree_gc.launchd.plist"
DEST="$HOME/Library/LaunchAgents/com.macro.worktree-gc.plist"

git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1 || { echo "$REPO_ROOT is not a git repo" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "missing template $TEMPLATE" >&2; exit 1; }

SUPPORT_DIR="$HOME/Library/Application Support/macro-worktree-gc"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/macro_worktree_gc" "$SUPPORT_DIR"
# The wrapper is HOST-INSTALLED plumbing: it re-extracts the tool and the config
# from origin/main on every run, so no checkout has to be current for policy to
# reach the sweep (the primary is routinely parked on an old commit).
cp "$SRC_DIR/worktree_gc_launchd.py" "$SUPPORT_DIR/"
sed -e "s|__REPO_ROOT__|$REPO_ROOT|g" -e "s|__HOME__|$HOME|g" -e "s|__SUPPORT_DIR__|$SUPPORT_DIR|g" "$TEMPLATE" > "$DEST"

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl print "gui/$UID_NUM/com.macro.worktree-gc" | head -5

echo "installed: $DEST (daily 05:17, logs in ~/Library/Logs/macro_worktree_gc/)"
echo "manual test run: launchctl kickstart gui/$UID_NUM/com.macro.worktree-gc"
echo "NOTE (macOS TCC): the repo lives under ~/Documents, which macOS shields from"
echo "background jobs. ONE-TIME: System Settings -> Privacy & Security -> Full Disk"
echo "Access -> + -> Cmd+Shift+G -> /usr/bin/python3 -> enable. Until granted, every"
echo "run fail-closes (deletes nothing) and the log names this exact step."
