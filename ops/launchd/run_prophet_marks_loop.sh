#!/bin/sh
# ops/launchd/run_prophet_marks_loop.sh — one Prophet marks publication cycle.
#
# Called every 5 minutes by com.mastermind.prophetmarks.plist (via run_with_env.sh).
# launchd's StartInterval is deliberately independent of the Mac's local timezone;
# this runner admits work only inside 09:25–16:05 America/New_York and exits after
# one cycle.  build_prophet_marks.py applies the stricter NYSE session/RTH guard.
#
# The explicit TZ is load-bearing: the production M1 is America/Vancouver.  Never
# replace this with the host-local clock or a launchd CalendarInterval hour.
#
# PYTHONPATH must include the repo root (set in the plist EnvironmentVariables).

export TZ=America/New_York

PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
MODULE="scripts.build_prophet_marks"
# Run the module from the same checkout that owns this launcher.  M1 installs
# this file from flow-ops-wt; a workstation-only absolute path makes every
# five-minute cycle fail before Python starts.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
WINDOW_OPEN_MINUTES=565   # 09:25 ET
WINDOW_CLOSE_MINUTES=965 # 16:05 ET (exclusive)

log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') [prophetmarks-cycle] $*"
}

HOUR=$(date +%H)
MINUTE=$(date +%M)
# Strip leading zeros before POSIX-shell arithmetic (08 and 09 must not be octal).
H=$(echo "$HOUR" | sed 's/^0*//')
M=$(echo "$MINUTE" | sed 's/^0*//')
H=${H:-0}
M=${M:-0}
NOW_MINUTES=$((H * 60 + M))

if [ "$NOW_MINUTES" -lt "$WINDOW_OPEN_MINUTES" ] || \
   [ "$NOW_MINUTES" -ge "$WINDOW_CLOSE_MINUTES" ]; then
    log "outside 09:25–16:05 ET window — cycle skipped"
    exit 0
fi

log "ET window admitted — firing build_prophet_marks --publish"
cd "$REPO_ROOT" && "$PYTHON" -m "$MODULE" --publish
RC=$?
log "build_prophet_marks exited rc=$RC"
exit "$RC"
