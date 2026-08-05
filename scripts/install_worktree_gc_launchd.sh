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

REPO_ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
TEMPLATE="$REPO_ROOT/scripts/worktree_gc.launchd.plist"
DEST="$HOME/Library/LaunchAgents/com.macro.worktree-gc.plist"

[ -f "$REPO_ROOT/scripts/worktree_gc.py" ] || { echo "no worktree_gc.py under $REPO_ROOT" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "missing template $TEMPLATE" >&2; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/macro_worktree_gc"
sed -e "s|__REPO_ROOT__|$REPO_ROOT|g" -e "s|__HOME__|$HOME|g" "$TEMPLATE" > "$DEST"

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl print "gui/$UID_NUM/com.macro.worktree-gc" | head -5

echo "installed: $DEST (daily 05:17, logs in ~/Library/Logs/macro_worktree_gc/)"
echo "manual test run: launchctl kickstart gui/$UID_NUM/com.macro.worktree-gc"
