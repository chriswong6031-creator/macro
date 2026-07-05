#!/usr/bin/env bash
# scripts/launchd/theta_backfill_keepalive.sh
#
# Guard wrapper for the ThetaData EOD backfill job.
# Invoked by launchd (com.macro.thetadata-backfill.plist) on login and after
# any exit of the prior instance.
#
# CONTRACT:
#   (a) If a backfill_thetadata_eod process is already running, EXIT immediately
#       — never spawn a duplicate; the launchd KeepAlive mechanism will retry
#       after the ThrottleInterval.
#   (b) Otherwise, cd to the ops worktree and resume the chained command:
#       ETF pass (22 named roots) → bare universe pass (all ~360 roots).
#       Both passes are idempotent — _backfill_state.json carries all progress.
#   (c) Log all output (stdout + stderr) to backfill.log in the ops worktree.
#       The log is append-only so prior run output is preserved for debugging.
#
# Install (once):
#   cp scripts/launchd/com.macro.thetadata-backfill.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
#
# Uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
#   rm ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist

set -euo pipefail

THETA_OPS_WT="/Users/chriswong/theta-ops-wt"
BACKFILL_LOG="${THETA_OPS_WT}/backfill.log"

# --- (a) Guard: exit if a backfill is already running -----------------------
if pgrep -f "backfill_thetadata_eod" > /dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: backfill_thetadata_eod already running — exiting (no duplicate)" \
        >> "${BACKFILL_LOG}"
    exit 0
fi

# --- (b) Resume the chained command ----------------------------------------
# ETF pass: 22 named roots (SPY QQQ IWM DIA + 11 sector XL* + SMH SOXX XBI KRE ARKK SPX SPXW)
# Bare universe pass: covers all ~360 roots from gex_symbols(); idempotent via _backfill_state.json
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: no live process found — resuming backfill" \
    >> "${BACKFILL_LOG}"

cd "${THETA_OPS_WT}"

# (c) Append all output to backfill.log
{
    python -m scripts.backfill_thetadata_eod \
        --roots SPY,QQQ,IWM,DIA,XLK,XLF,XLE,XLI,XLU,XLV,XLY,XLP,XLB,XLC,XLRE,SMH,SOXX,XBI,KRE,ARKK,SPX,SPXW \
    && python -m scripts.backfill_thetadata_eod
} >> "${BACKFILL_LOG}" 2>&1

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: chained command exited (status=$?)" \
    >> "${BACKFILL_LOG}"
