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
#   (b) TIMING GATE: If the current UTC time is before 20:10 UTC (= 13:10 PT /
#       16:10 ET), exit 1 — launchd retries after ThrottleInterval (60s).
#       This prevents heavy API pulls from competing with the live-flow poller
#       which runs 09:25–16:05 ET on RTH days.
#   (c) If a backfill_thetadata_eod process is already running, EXIT immediately
#       — never spawn a duplicate; launchd will retry after ThrottleInterval.
#   (d) Before the ETF pass, unmark the current year from _backfill_state.json
#       for the 22 ETF anchors so they are always re-pulled with today's data.
#       The backfill marks a year "complete" on first pull and would otherwise
#       skip it; unmarking forces a fresh pull (overwrites the year parquet).
#   (e) Run the chained command:
#       ETF pass (22 named roots) → bare universe pass (all ~360 roots).
#       Both passes are idempotent — _backfill_state.json carries all progress.
#   (f) Log all output to backfill.log (append-only).
#
# PYTHON PATH: launchd's PATH is /usr/bin:/bin:/usr/sbin:/sbin — bare 'python'
#   is not found (exit 127).  Use the full conda path explicitly.
#
# Install (once):
#   cp scripts/launchd/com.macro.thetadata-backfill.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
#
# Uninstall:
#   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist
#   rm ~/Library/LaunchAgents/com.macro.thetadata-backfill.plist

set -uo pipefail

THETA_OPS_WT="/Users/chriswong/theta-ops-wt"
BACKFILL_LOG="${THETA_OPS_WT}/backfill.log"
MANIFEST="${THETA_OPS_WT}/data/thetadata_eod/_manifest.json"
STATE="${THETA_OPS_WT}/data/thetadata_eod/_backfill_state.json"

# Full path to the conda python that has pandas/pyarrow/requests.
# launchd's PATH is /usr/bin:/bin:/usr/sbin:/sbin — bare 'python' is not found.
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"

# 22 ETF anchors always re-pulled post-close to get today's greeks.
ETF_ROOTS="SPY,QQQ,IWM,DIA,XLK,XLF,XLE,XLI,XLU,XLV,XLY,XLP,XLB,XLC,XLRE,SMH,SOXX,XBI,KRE,ARKK,SPX,SPXW"

# --- (a) Completion guard: exit 0 if universe pass is already done ----------
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

# --- (b) TIMING GATE: do not run before 20:10 UTC (13:10 PT / 16:10 ET) -----
current_hhmm=$(date -u +%H%M)
if [ "${current_hhmm}" -lt "2010" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: pre-close gate (UTC ${current_hhmm} < 2010) — deferring" \
        >> "${BACKFILL_LOG}"
    exit 1
fi

# --- (c) Guard: exit if a backfill is already running -----------------------
if pgrep -f "backfill_thetadata_eod" > /dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: backfill_thetadata_eod already running — exiting (no duplicate)" \
        >> "${BACKFILL_LOG}"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: post-close gate passed — starting backfill" \
    >> "${BACKFILL_LOG}"

cd "${THETA_OPS_WT}"

# --- (d) Unmark current year for ETF anchors so ETF pass re-pulls today -----
current_year=$(date +%Y)
CURRENT_YEAR="${current_year}" THETA_STATE="${STATE}" ETF_ROOTS="${ETF_ROOTS}" \
"${PYTHON}" -c "
import json, os, sys

state_path = os.environ['THETA_STATE']
yr = os.environ['CURRENT_YEAR']
etf_roots = [r.strip().upper() for r in os.environ['ETF_ROOTS'].split(',') if r.strip()]

try:
    with open(state_path) as f:
        state = json.load(f)
except Exception as e:
    print(f'[state_reset] ERROR reading state: {e}', flush=True)
    sys.exit(0)

changed = []
for root in etf_roots:
    years = state.get('completed', {}).get(root, [])
    if yr in years:
        state['completed'][root] = [y for y in years if y != yr]
        changed.append(root)

if changed:
    with open(state_path, 'w') as f:
        json.dump(state, f)
    print(f'[state_reset] Unmarked year={yr} for {len(changed)} ETF roots: {changed}', flush=True)
else:
    print(f'[state_reset] year={yr} not present in state for ETF roots — no change needed', flush=True)
" >> "${BACKFILL_LOG}" 2>&1

# --- (e) Run chained command: ETF pass → universe pass ----------------------
rc=0
{
    "${PYTHON}" -m scripts.backfill_thetadata_eod --roots "${ETF_ROOTS}" \
    && "${PYTHON}" -m scripts.backfill_thetadata_eod
} >> "${BACKFILL_LOG}" 2>&1 || rc=$?

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] theta_backfill_keepalive: chained command exited (status=${rc})" \
    >> "${BACKFILL_LOG}"

exit ${rc}
