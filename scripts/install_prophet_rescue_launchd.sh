#!/bin/bash
# Install the per-host Prophet US rescue launchd agent (OPERATOR-RUN).
#
# Usage: bash scripts/install_prophet_rescue_launchd.sh [/path/to/primary/checkout]
#
# Installs ~/Library/LaunchAgents/com.macro.prophet-rescue.plist, running the
# rescue lane twice daily (19:10 and 05:10 local).  This is the HOST half of the
# availability pair: .github/workflows/prophet-rescue.yml is GitHub-hosted and
# survives the Mac Studio dying; this one survives GitHub's scheduler dying and
# adds the disk-headroom check only a host can make.
#
# NOTHING INSTALLS THIS AUTOMATICALLY, and nothing should.  The lane can DISPATCH
# daily.yml, so arming a second dispatcher on a host is an operator act — sessions
# must not run this unprompted (same protocol as the worktree-GC agent,
# research/WORKTREE_GC_POLICY.md).
set -euo pipefail

# REPO_ROOT = the GIT VANTAGE POINT (where origin/main is fetched from), and the
# volume whose free space the lane reports on.  Source files come from THIS
# installer's own checkout (SRC_DIR): the primary is routinely parked on a commit
# that predates the tool, so it can never be the source of code.  The wrapper
# re-extracts tool + dependency from origin/main at every run.
REPO_ROOT="${1:-/Users/chriswong/Documents/Cluade/Macro Dashboard}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SRC_DIR/prophet_rescue.launchd.plist"
DEST="$HOME/Library/LaunchAgents/com.macro.prophet-rescue.plist"

git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1 || { echo "$REPO_ROOT is not a git repo" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "missing template $TEMPLATE" >&2; exit 1; }

SUPPORT_DIR="$HOME/Library/Application Support/macro-prophet-rescue"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/macro_prophet_rescue" "$SUPPORT_DIR"
# The wrapper is HOST-INSTALLED plumbing: it re-extracts the tool from origin/main
# on every run, so no checkout has to be current for the right policy to run.
cp "$SRC_DIR/prophet_rescue_launchd.py" "$SUPPORT_DIR/"
sed -e "s|__REPO_ROOT__|$REPO_ROOT|g" -e "s|__HOME__|$HOME|g" -e "s|__SUPPORT_DIR__|$SUPPORT_DIR|g" "$TEMPLATE" > "$DEST"

# Secrets live in a chmod-600 host file, never in the plist (which is
# world-readable) and never in the repo.  Created empty so the operator has
# somewhere obvious to put them; an absent/empty file is fine — the lane then
# borrows `gh auth token` for reads and skips the push transports.
if [ ! -f "$SUPPORT_DIR/env" ]; then
  cat > "$SUPPORT_DIR/env" <<'ENVEOF'
# Prophet rescue host lane — KEY=VALUE, one per line. Optional.
# Same names heartbeat.yml passes to scripts/healthcheck.py.
# GH_TOKEN=
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_CHAT_ID=
# DISCORD_WEBHOOK_URL=
# DISCORD_WEBHOOK_WATCHLIST=
ENVEOF
fi
chmod 600 "$SUPPORT_DIR/env"

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl print "gui/$UID_NUM/com.macro.prophet-rescue" | head -5

echo "installed: $DEST (19:10 + 05:10 local, logs in ~/Library/Logs/macro_prophet_rescue/)"
echo "secrets (optional): $SUPPORT_DIR/env  [chmod 600]"
echo "manual test run: launchctl kickstart gui/$UID_NUM/com.macro.prophet-rescue"
echo "dry probe without launchd: python3 \"$SUPPORT_DIR/prophet_rescue_launchd.py\""
echo "NOTE (macOS TCC): the repo lives under ~/Documents, which macOS shields from"
echo "background jobs. ONE-TIME: System Settings -> Privacy & Security -> Full Disk"
echo "Access -> + -> Cmd+Shift+G -> /usr/bin/python3 -> enable. Until granted, every"
echo "run fail-closes (dispatches nothing) and the log names this exact step."
