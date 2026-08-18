#!/bin/bash
# Install the host-native PRIMARY clock for the evening close pass (OPERATOR-RUN).
#
# Usage: bash scripts/install_closepass_launchd.sh [/path/to/primary/checkout]
#
# Installs ~/Library/LaunchAgents/com.macro.closepass.plist, firing the close
# pass at 13:00 local (PT) Monday-Friday — which is 16:00 ET in BOTH DST regimes,
# because PT and ET flip together and the offset between them is a constant -3h.
#
# WHY A HOST CLOCK.  .github/workflows/close-pass.yml was the product clock and
# cannot be one.  Measured Friday 2026-08-14: the 20:25 UTC cron line's run was
# CREATED at 20:52 (27 min of scheduler drift), its DST sibling at 21:47 then sat
# 95 minutes in the queue, and the board published ~19:20 ET against a 16:15 ET
# product target.  Estate-wide the measurement is worse — GitHub cron gaps of
# 90 min to 3h12m, agentos/decisions/DEC-LER-LIVE-LANE-VPS-5MIN-REST.md.  After
# this installs, the workflow is a BOUNDED BACKSTOP: it fast-exits when this lane
# already landed the session's board, and announces loudly when it had to publish.
#
# NOTHING INSTALLS THIS AUTOMATICALLY, and nothing should.  Arming a scheduled
# publisher on a host is an operator act — sessions must not run this unprompted
# (same protocol as the prophet-rescue agent and the worktree-GC agent,
# research/WORKTREE_GC_POLICY.md).  The doctrine is unchanged by the fact that
# this particular program was ORDERED: the Chairman directive of 2026-08-15
# (Breathing Platform revival §6) commissioned the host-native clock, and the
# building session still hands the installer to the operator rather than running
# it.  Ordering the design is not the same act as arming the host.
set -euo pipefail

# REPO_ROOT = the GIT VANTAGE POINT (where origin/main is fetched from) and the
# home of the chmod-600 .env the lane sources.  It is NEVER the source of code
# that runs: the primary is routinely parked on an old commit, so the runner
# resets a locked worktree under it to origin/main on every run and publishes
# from there.  Source files come from THIS installer's own checkout (SRC_DIR).
REPO_ROOT="${1:-/Users/chriswong/Documents/Cluade/Macro Dashboard}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_SRC="$(cd "$SRC_DIR/.." && pwd)"
TEMPLATE="$REPO_SRC/ops/launchd/com.macro.closepass.plist"
DEST="$HOME/Library/LaunchAgents/com.macro.closepass.plist"

git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1 || { echo "$REPO_ROOT is not a git repo" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "missing template $TEMPLATE" >&2; exit 1; }

SUPPORT_DIR="$HOME/Library/Application Support/macro-closepass"
LOG_DIR="$HOME/Library/Logs/macro_closepass"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$SUPPORT_DIR/runs"

# The runner is HOST-INSTALLED PLUMBING and lives OUTSIDE ~/Documents on purpose:
# launchd jobs cannot exec from there at all (the wall
# ops/launchd/com.macro.chainheat.plist documents).  It is frozen at install
# time — re-run this installer after editing scripts/close_pass_host_runner.py.
# The POLICY it launches is never this vintage: the runner resets its lane
# checkout to origin/main every run, and the copy of this same file INSIDE that
# lane is what answers --probe-close.
#
# THIS cp IS THE ONLY ACT THAT DEPLOYS THIS FILE, and that is the freeze working
# as designed -- but on 2026-08-18 it also meant PR #5862 merged as af416e4a1066
# while the host kept executing the pre-fix bytes from Aug 15 19:54, invisibly,
# because nothing compared the two.  Every receipt now carries a `bootstrap`
# block (file_sha256 + mtime of the EXECUTING snapshot, graded against
# origin/main every run) alongside `code_sha` (the lane's git HEAD), and
# scripts/close_pass_slo_report.py fails its bootstrap leg on drift.  The names
# are deliberately un-confusable: one says file_sha256, the other says code_sha.
#
# So SAY what this install moved.  "Already at this vintage" and "deployed" look
# identical from the outside and only one of them means a merged fix went live.
NEW_SHA="$(shasum -a 256 "$REPO_SRC/scripts/close_pass_host_runner.py" | awk '{print $1}')"
OLD_SHA="$(shasum -a 256 "$SUPPORT_DIR/close_pass_host_runner.py" 2>/dev/null | awk '{print $1}' || true)"
cp "$REPO_SRC/scripts/close_pass_host_runner.py" "$SUPPORT_DIR/"
chmod 755 "$SUPPORT_DIR/close_pass_host_runner.py"
if [ -z "${OLD_SHA:-}" ]; then
  echo "runner: first install (file_sha256 ${NEW_SHA:0:12})"
elif [ "$OLD_SHA" = "$NEW_SHA" ]; then
  echo "runner: already at this vintage (file_sha256 ${NEW_SHA:0:12}) - snapshot unchanged"
else
  echo "runner: DEPLOYED ${OLD_SHA:0:12} -> ${NEW_SHA:0:12} (the frozen snapshot moved)"
fi

sed -e "s|__HOME__|$HOME|g" -e "s|__SUPPORT_DIR__|$SUPPORT_DIR|g" "$TEMPLATE" > "$DEST"
plutil -lint "$DEST"

# Secrets stay in the primary checkout's chmod-600 .env — never in the plist
# (world-readable) and never in the repo.  The installer only checks that the
# file exists and is not group/world readable; it NEVER reads or prints a value.
ENV_FILE="$REPO_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "WARNING: $ENV_FILE is absent — the pass will have no R2 credentials and" >&2
  echo "         every run will publish nothing.  Provision it before arming." >&2
else
  MODE="$(stat -f '%Lp' "$ENV_FILE")"
  [ "$MODE" = "600" ] || echo "WARNING: $ENV_FILE is mode $MODE — expected 600" >&2
fi

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$DEST"
launchctl print "gui/$UID_NUM/com.macro.closepass" | head -5

echo "installed: $DEST (13:00 local Mon-Fri = 16:00 ET year-round)"
echo "logs:      $LOG_DIR/launchd.{out,err}.log"
echo "receipts:  $SUPPORT_DIR/runs/<session>.json"
echo "manual test run:   launchctl kickstart gui/$UID_NUM/com.macro.closepass"
echo "dry probe (no publish, no launchd):"
echo "  /usr/bin/python3 \"$SUPPORT_DIR/close_pass_host_runner.py\" --dry-run"
echo "verify the deployed vintage IS this checkout (merging alone never deploys it):"
echo "  shasum -a 256 \"$SUPPORT_DIR/close_pass_host_runner.py\" \"$REPO_SRC/scripts/close_pass_host_runner.py\""
echo "drift leg (grades the newest run receipt, exits 1 on drift):"
echo "  python3 -m scripts.close_pass_slo_report --sessions 3"
echo "rollback:  launchctl bootout gui/$UID_NUM/com.macro.closepass"
echo "           rm \"$DEST\""
echo "           git -C \"$REPO_ROOT\" worktree remove --force .claude/worktrees/closepass-host-lane"
echo "           (the lane worktree is created --lock'd so the fleet GC leaves it alone;"
echo "            'worktree remove --force' is required while that lock stands)"
echo "NOTE (macOS TCC): the repo lives under ~/Documents, which macOS shields from"
echo "background jobs. ONE-TIME: System Settings -> Privacy & Security -> Full Disk"
echo "Access -> + -> Cmd+Shift+G -> /usr/bin/python3 -> enable. Until granted, every"
echo "run fail-closes (publishes nothing) and the log names this exact step."
