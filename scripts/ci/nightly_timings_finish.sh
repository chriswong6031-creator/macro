# shellcheck shell=bash
# ---------------------------------------------------------------------------
# scripts/ci/nightly_timings_finish.sh <cap-minutes> — a nightly job's LAST step
# (if: always()). W2 of NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN.
#
#   1. python3 scripts/nightly_timings.py finish — appends this job's row to
#      data/ops/nightly_timings/<job>.jsonl and emits the line-start ::warning
#      when elapsed exceeds 85% of the cap (the annotation lives in the Python,
#      bare print, per tests/test_gh_annotation_line_start.py).
#   2. commits + pushes ONLY that per-job ledger file with the shared retry
#      policy (scripts/ci/push_retry.sh). Per-job files mean two daily jobs can
#      never conflict on the same ledger append.
#
# The job name comes from GITHUB_JOB (no per-job copy-paste to drift); the cap
# argument is pinned to the job's timeout-minutes by tests/test_nightly_timings.py.
# Everything here is non-fatal by design: telemetry must never cost a night.
# Invoked with `bash`, so no shebang/executable bit is load-bearing.
# ---------------------------------------------------------------------------
set -u

CAP="${1:?usage: nightly_timings_finish.sh <cap-minutes>}"
JOB="${GITHUB_JOB:-local}"
LEDGER="data/ops/nightly_timings/${JOB}.jsonl"

python3 scripts/nightly_timings.py finish --cap-minutes "$CAP" || {
  echo "::warning title=nightly timings finish failed::${JOB}: finish exited $? — no timings row this night (non-fatal)"
  exit 0
}

# Only publish from a real Actions run — a local invocation writes the row and stops.
if [ "${GITHUB_ACTIONS:-}" != "true" ]; then
  echo "not in GitHub Actions — ledger row written locally, commit/push skipped"
  exit 0
fi
[ -f "$LEDGER" ] || { echo "no ledger row written — nothing to commit"; exit 0; }

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
git add "$LEDGER"
if git diff --cached --quiet; then echo "no timings changes to commit"; exit 0; fi
git commit -m "data: nightly timings ${JOB} $(date -u +%F)" || {
  echo "::warning::nightly timings commit failed for ${JOB} (non-fatal)"
  exit 0
}
# Small, fast budgets: this is a ~200-byte append racing lanes that commit to
# main every 1-2 minutes. -X theirs + autostash mirror the job commit steps;
# leftover tracked dirt from earlier steps parks across the rebase exactly as
# it does in the "push market data" loop.
PUSH_ALARM=120
PUSH_BUDGET_SECS=240
push_retry_init "nightly timings ${JOB}"
while push_attempt; do
  perl -e 'alarm 60; exec @ARGV or die' -- git fetch origin main || true
  comm -12 <(git ls-files --others --exclude-standard | LC_ALL=C sort) \
           <(git ls-tree -r --name-only origin/main | LC_ALL=C sort) \
    | while IFS= read -r f; do rm -f -- "$f" || true; done
  if perl -e 'alarm 180; exec @ARGV or die' -- git pull --rebase --autostash -X theirs origin main && push_autostash_ok; then
    if push_do; then echo "pushed nightly timings (${JOB}) on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
  fi
  push_abort_rebase
  push_backoff
done
push_lost
echo "::warning::could not push nightly timings for ${JOB} after $PUSH_ATTEMPT attempts ($PUSH_STOP) (non-fatal — tonight's row is lost at the next clean checkout; the trend resumes tomorrow)"
exit 0
