#!/usr/bin/env bash
# scripts/launchd/theta_backfill_keepalive.sh
#
# Guard wrapper for the ThetaData EOD backfill job.
# Invoked by launchd (com.macro.thetadata-backfill.plist) on login and after
# any exit of the prior instance.
#
# CONTRACT:
#   (a) If the universe pass is already marked complete in _manifest.json,
#       EXIT 0 without resuming — launchd will NOT restart (KeepAlive uses
#       SuccessfulExit=false, so exit-0 is treated as "done").
#   (b) If a backfill_thetadata_eod process is already running, EXIT immediately
#       — never spawn a duplicate; launchd will retry after ThrottleInterval.
#   (c) Otherwise, cd to the ops worktree and resume the chained command:
#       ETF pass (22 named roots) → bare universe pass (all ~360 roots).
#       Both passes are idempotent — _backfill_state.json carries all progress.
#   (d) Log all output (stdout + stderr) to backfill.log in the ops worktree.
#       The log is append-only so prior run output is preserved for debugging.
#
# Install (once):
#   cp scripts/launchd/com.macro.thetadata-backfill.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
#
# Uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
#   rm ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist

set -uo pipefail

THETA_OPS_WT="/Users/chriswong/theta-ops-wt"
BACKFILL_LOG="${THETA_OPS_WT}/backfill.log"
MANIFEST="${THETA_OPS_WT}/data/thetadata_eod/_manifest.json"

# --- (a) Completion guard: exit 0 if universe pass is already done ----------
# launchd is configured with KeepAlive={SuccessfulExit=false}, so exit 0 here
# stops further restarts — no infinite loop once the universe pass completes.
if [ -f "${MANIFEST}" ]; then
    universe_complete=$(python3 -c "
import json, sys
try:
    d = json.load(open('${MANIFEST}'))
    print('1' if d.get('universe_pass_complete') else '0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")
    if [ "${universe_complete}" = "1" ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: universe pass complete per _manifest.json — exiting cleanly (no restart)" \
            >> "${BACKFILL_LOG}"
        exit 0
    fi
fi

# --- (b) Guard: exit if a backfill is already running -----------------------
if pgrep -f "backfill_thetadata_eod" > /dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: backfill_thetadata_eod already running — exiting (no duplicate)" \
        >> "${BACKFILL_LOG}"
    exit 1
fi

# --- (c) Resume the chained command ----------------------------------------
# ETF pass: 22 named roots (SPY QQQ IWM DIA + 11 sector XL* + SMH SOXX XBI KRE ARKK SPX SPXW)
# Bare universe pass: covers all ~360 roots from gex_symbols(); idempotent via _backfill_state.json
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: no live process found — resuming backfill" \
    >> "${BACKFILL_LOG}"

cd "${THETA_OPS_WT}"

# (d) Append all output to backfill.log; capture exit code so it always logs
rc=0
{
    python -m scripts.backfill_thetadata_eod \
        --roots SPY,QQQ,IWM,DIA,XLK,XLF,XLE,XLI,XLU,XLV,XLY,XLP,XLB,XLC,XLRE,SMH,SOXX,XBI,KRE,ARKK,SPX,SPXW \
    && python -m scripts.backfill_thetadata_eod
} >> "${BACKFILL_LOG}" 2>&1 || rc=$?

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: chained command exited (status=${rc})" \
    >> "${BACKFILL_LOG}"

exit ${rc}
