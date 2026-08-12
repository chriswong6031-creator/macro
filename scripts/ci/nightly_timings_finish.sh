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
#
# NON-FATAL IS NOT SILENT. Every early exit below is `exit 0` AND a line-start
# bare `echo "::warning ..."` — never through a logger, which would push the ::
# off column 0 and make GitHub drop it (tests/test_gh_annotation_line_start.py).
# A telemetry step that loses a night's row without saying so is the same class
# of defect as the dark tripwire it is here to prevent: the engine job's row was
# missing for three nights while every path in this script reported success.
#
# Step ORDER matters as much as the exits: this step must run BEFORE any heavy
# always() delivery step in its job (engine's `upload pages artifact`), because
# on a cap-cancel night the runner's ~5-minute grace is all the time the whole
# always() tail gets — see the comment on the engine job's finish step in
# .github/workflows/daily.yml.
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
[ -f "$LEDGER" ] || {
  echo "::warning title=nightly timings row missing::${JOB}: finish exited 0 but ${LEDGER} does not exist — no row to commit, so tonight's elapsed time and the 85% tripwire trend are lost (non-fatal)"
  exit 0
}

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
# Source-only: provides the exact private-index candidate builder; its intrinsic
# BASH_SOURCE guard prevents command dispatch while sourced.
. "${GITHUB_WORKSPACE:-.}/scripts/ci/options_signal_nightly.sh"
# The helper is fail-closed and enables errexit for workflow commands.  Timing
# telemetry is intentionally non-fatal, so restore this script's original mode.
set +e
git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
if [ "$(git symbolic-ref -q HEAD 2>/dev/null || true)" != refs/heads/main ]; then
  echo "::warning title=nightly timings wrong ref::${JOB}: authoritative timing publication requires exact symbolic main; row remains local"
  exit 0
fi
git add "$LEDGER"
# A row was appended a few lines ago, so an empty stage means git cannot SEE it
# (ignored path, wrong workspace, a `git checkout`/reset by an earlier step).
# That is a silent loss, not a no-op — say so.
if git diff --cached --quiet -- "$LEDGER"; then
  echo "::warning title=nightly timings not staged::${JOB}: ${LEDGER} was written but git staged no change — the row exists only in the runner workspace and dies at the next clean checkout (non-fatal)"
  exit 0
fi
TIMING_PARENT=$(git rev-parse 'HEAD^{commit}') || exit 0
TIMING_MESSAGE="data: nightly timings ${JOB} $(date -u +%F)"
TIMING_CANDIDATE_INDEX="${RUNNER_TEMP:-/tmp}/nightly-timing-candidate-${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}.idx"
TIMING_COMMIT=$(oip_exact_candidate_commit \
  "$TIMING_PARENT" "$TIMING_MESSAGE" "$TIMING_CANDIDATE_INDEX" "$LEDGER") || {
  echo "::warning title=nightly timings commit failed::${JOB}: exact ledger candidate could not be built — row remains local"
  exit 0
}
git reset -q -- "$LEDGER" || {
  echo "::warning title=nightly timings reset failed::${JOB}: exact candidate built but the live index could not be cleared; no push attempted"
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
  if ! perl -e 'alarm 60; exec @ARGV or die' -- git fetch origin \
      +refs/heads/main:refs/remotes/origin/main; then
    push_backoff
    continue
  fi
  TIMING_REPLAY_INDEX="${RUNNER_TEMP:-/tmp}/nightly-timing-replay-${GITHUB_RUN_ID:-local}-${GITHUB_JOB:-job}.idx"
  if TIMING_PUBLISH=$(push_exact_paths_replay_commit \
      "$TIMING_PARENT" origin/main "$TIMING_COMMIT" "$TIMING_MESSAGE" \
      "$TIMING_REPLAY_INDEX" "$LEDGER"); then
    if [ "$(git rev-parse "$TIMING_PUBLISH^{tree}")" = \
         "$(git rev-parse 'origin/main^{tree}')" ]; then
      echo "nightly timings (${JOB}) already on origin/main"
      push_won
      exit 0
    fi
    if push_do origin "$TIMING_PUBLISH:refs/heads/main"; then
      echo "pushed nightly timings (${JOB}) on attempt $PUSH_ATTEMPT"
      push_won
      exit 0
    fi
  else
    PUSH_FAIL_CLASS="rebase-conflict"
  fi
  push_backoff
done
push_lost
echo "::warning title=nightly timings push lost::could not push nightly timings for ${JOB} after $PUSH_ATTEMPT attempts ($PUSH_STOP) (non-fatal — tonight's row is lost at the next clean checkout; the trend resumes tomorrow)"
exit 0
