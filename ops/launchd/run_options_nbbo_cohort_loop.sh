#!/bin/sh
# One host-private same-basis OPRA NBBO cohort cycle.
#
# launchd fires every 300 seconds.  This runner uses the exchange timezone and
# admits 09:25-16:05 ET so the 09:30 capture and 16:00 session finalization both
# occur.  Python applies the exact NYSE-session and RTH guards.

export TZ=America/New_York

PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
MODULE="scripts.capture_options_nbbo_cohort"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
EXPECTED_REPO_ROOT="/Users/chriswong/options-nbbo-ops-wt"
PRIVATE_ROOT="${OPTIONS_NBBO_COHORT_PRIVATE_ROOT:-/Users/chriswong/.mastermind_private/options_nbbo_cohort_v1}"
WINDOW_OPEN_MINUTES=565
WINDOW_CLOSE_MINUTES=965

log() {
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') [options-nbbo-cohort] $*"
}

if [ "$REPO_ROOT" != "$EXPECTED_REPO_ROOT" ]; then
    log "refused non-dedicated checkout root=$REPO_ROOT"
    exit 1
fi

CHECKOUT_SHA=$(/usr/bin/git -C "$REPO_ROOT" rev-parse HEAD) || exit 1
if [ -n "$(/usr/bin/git -C "$REPO_ROOT" status --porcelain)" ]; then
    log "refused dirty operational checkout sha=$CHECKOUT_SHA"
    exit 1
fi
RUNNER_SHA=$(/usr/bin/shasum -a 256 "$SCRIPT_DIR/run_options_nbbo_cohort_loop.sh" | /usr/bin/awk '{print $1}')
SCHEMA_SHA=$(/usr/bin/shasum -a 256 "$REPO_ROOT/contracts/options/options.prospective_nbbo_cohort.v1.schema.json" | /usr/bin/awk '{print $1}')
log "installed checkout_sha=$CHECKOUT_SHA runner_sha256=$RUNNER_SHA schema_sha256=$SCHEMA_SHA"

HOUR=$(date +%H)
MINUTE=$(date +%M)
H=$(echo "$HOUR" | sed 's/^0*//')
M=$(echo "$MINUTE" | sed 's/^0*//')
H=${H:-0}
M=${M:-0}
NOW_MINUTES=$((H * 60 + M))

if [ "$NOW_MINUTES" -lt "$WINDOW_OPEN_MINUTES" ] || \
   [ "$NOW_MINUTES" -ge "$WINDOW_CLOSE_MINUTES" ]; then
    log "outside 09:25-16:05 ET window - cycle skipped"
    exit 0
fi

cd "$REPO_ROOT" || exit 1

"$PYTHON" -m "$MODULE" --private-root "$PRIVATE_ROOT" --initialize
INIT_RC=$?
if [ "$INIT_RC" -ne 0 ]; then
    log "initialize refused rc=$INIT_RC"
    exit "$INIT_RC"
fi

# Empty-safe liveness receipt.  This explicitly records both producers as
# unavailable; it never converts an absent authenticated producer into a
# successful zero-call poll or selector abstention.
"$PYTHON" -m "$MODULE" --private-root "$PRIVATE_ROOT" --record-unavailable-cycle
CAPTURE_RC=$?

# The only internally generated terminal is the frozen 15:55 ET expiry event.
"$PYTHON" -m "$MODULE" --private-root "$PRIVATE_ROOT" --expire-open
EXPIRY_RC=$?

"$PYTHON" -m "$MODULE" --private-root "$PRIVATE_ROOT" --advance
ADVANCE_RC=$?

log "cycle complete capture=$CAPTURE_RC expiry=$EXPIRY_RC advance=$ADVANCE_RC"
if [ "$CAPTURE_RC" -ne 0 ]; then
    exit "$CAPTURE_RC"
fi
if [ "$EXPIRY_RC" -ne 0 ]; then
    exit "$EXPIRY_RC"
fi
exit "$ADVANCE_RC"
