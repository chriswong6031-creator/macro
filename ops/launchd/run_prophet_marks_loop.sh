#!/bin/sh
# ops/launchd/run_prophet_marks_loop.sh — RTH polling loop for the Prophet marks publisher.
#
# Called by com.mastermind.prophetmarks.plist (via run_with_env.sh) at 09:25 ET weekdays.
# Runs build_prophet_marks --publish every 5 minutes until 16:05 ET, then exits.
# launchd fires this again at 09:25 the next weekday.
#
# RTH guard: build_prophet_marks.py has its own is_rth_now() check; cycles before
# 09:30 ET or after 16:00 ET log "outside RTH" and exit 0 cleanly.  The loop here
# exits when the system clock passes 16:05 ET to avoid running the script indefinitely.
#
# TIMEZONE ASSUMPTION: `date +%H` and the StartCalendarInterval in the plist both use
# the Mac system timezone.  This script assumes the system is set to America/New_York.
# (Matches the established com.mastermind.liveflow.plist convention.)  If the system
# timezone ever changes, the 09:25 start and 16:05 cutoff will shift silently.
#
# PYTHONPATH must include the repo root (set in the plist EnvironmentVariables).

PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
MODULE="scripts.build_prophet_marks"
# Repo root — build_prophet_marks.py resolves lib/nyse_calendar via
# Path(__file__).parent.parent; cd here before invoking so _REPO is correct
# when the deployed script lives in flow-ops-wt (which lacks lib/nyse_calendar).
REPO_ROOT="/Users/chriswong/Documents/Cluade/Macro Dashboard"
INTERVAL=300   # 5 minutes in seconds
# Cutoff hour:minute in ET (24h); we compare against 'date' output
CUTOFF_HOUR=16
CUTOFF_MIN=5

log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S') [prophetmarks-loop] $*"
}

log "loop started (PID=$$, interval=${INTERVAL}s, cutoff=${CUTOFF_HOUR}:$(printf '%02d' $CUTOFF_MIN) ET)"

while true; do
    # Check exit condition: current ET time >= 16:05
    # 'date' uses system timezone; the Mac should be set to America/New_York.
    HOUR=$(date +%H)
    MIN=$(date +%M)
    # Arithmetic comparison (strip leading zeros to avoid octal parse)
    H=$(echo "$HOUR" | sed 's/^0*//')
    M=$(echo "$MIN"  | sed 's/^0*//')
    H=${H:-0}
    M=${M:-0}

    if [ "$H" -gt "$CUTOFF_HOUR" ] || \
       { [ "$H" -eq "$CUTOFF_HOUR" ] && [ "$M" -ge "$CUTOFF_MIN" ]; }; then
        log "past ${CUTOFF_HOUR}:$(printf '%02d' $CUTOFF_MIN) ET — loop exiting"
        exit 0
    fi

    log "firing build_prophet_marks --publish"
    cd "$REPO_ROOT" && "$PYTHON" -m "$MODULE" --publish
    RC=$?
    log "build_prophet_marks exited rc=$RC"

    log "sleeping ${INTERVAL}s"
    sleep "$INTERVAL"
done
