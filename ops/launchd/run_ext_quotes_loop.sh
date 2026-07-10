#!/bin/sh
# ops/launchd/run_ext_quotes_loop.sh — ext-hours polling loop for the ext-quotes publisher.
#
# Called by com.macro.extquotes.plist (via run_with_env.sh).
# Runs build_ext_quotes --publish every 2 minutes while inside an ext-hours window;
# exits when neither pre-market (04:00–09:30 ET) nor post-market (16:00–20:00 ET).
#
# The script fires on both launchd windows (pre and post) and self-exits when the
# current time leaves both ext windows, so launchd does not need explicit end times.
#
# TIMEZONE ASSUMPTION: `date +%H` and StartCalendarInterval in the plist both use
# the Mac system timezone, assumed to be America/New_York (same convention as
# com.mastermind.prophetmarks.plist).
#
# PYTHONPATH must include the repo root (set in the plist EnvironmentVariables).

PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
MODULE="scripts.build_ext_quotes"
REPO_ROOT="/Users/chriswong/Documents/Cluade/Macro Dashboard"
INTERVAL=120   # 2 minutes in seconds

log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S') [extquotes-loop] $*"
}

# Returns 0 if current ET time is in a pre-market or post-market ext window,
# 1 otherwise.  Uses simple hour/minute arithmetic; Mac system tz = America/New_York.
in_ext_window() {
    H=$(date +%H | sed 's/^0*//')
    M=$(date +%M | sed 's/^0*//')
    H=${H:-0}
    M=${M:-0}
    MINS=$((H * 60 + M))
    # Pre-market: [04:00, 09:30)  → [240, 570)
    if [ "$MINS" -ge 240 ] && [ "$MINS" -lt 570 ]; then
        return 0
    fi
    # Post-market: [16:00, 20:00) → [960, 1200)
    if [ "$MINS" -ge 960 ] && [ "$MINS" -lt 1200 ]; then
        return 0
    fi
    return 1
}

log "loop started (PID=$$, interval=${INTERVAL}s)"

while true; do
    if ! in_ext_window; then
        log "outside ext windows — loop exiting"
        exit 0
    fi

    log "firing build_ext_quotes --publish"
    cd "$REPO_ROOT" && "$PYTHON" -m "$MODULE" --publish
    RC=$?
    log "build_ext_quotes exited rc=$RC"

    log "sleeping ${INTERVAL}s"
    sleep "$INTERVAL"
done
