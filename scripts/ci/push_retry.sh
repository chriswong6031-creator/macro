# shellcheck shell=bash
# ---------------------------------------------------------------------------
# scripts/ci/push_retry.sh — shared retry policy for the lane commit→push loops.
#
# SOURCE this (never execute it) from a workflow `run:` block:
#
#     . "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
#     push_retry_init "rendered site"
#     while push_attempt; do
#       git fetch origin main || true
#       <pre-sync collision sweep>
#       if git pull --rebase --autostash -X theirs origin main \
#            || bash scripts/rebase_autoresolve_hashed_css.sh; then
#         <post-rebase guards>
#         if push_do; then echo "pushed ... on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
#       fi
#       push_abort_rebase
#       push_backoff
#     done
#     push_lost
#     echo "::error ...::$PUSH_ATTEMPT rebase/push attempts failed — ..."
#
# WHY (2026-07-25, render.yml run 30167139398): a scope=all render built every page
# CORRECTLY — 1121 locked special-situations rows, a fresh site/premiumdata — and then
# lost ALL FIVE push attempts to
#
#     ! [remote rejected] main -> main (cannot lock ref 'refs/heads/main':
#       is at <X> but expected <Y>)
#
# ~95 minutes of render discarded under a red X that reads like a conflict. It was not
# one. That rejection is a LOST RACE for the ref against the many lanes that commit to
# main every 1–2 minutes (agent branches, marketing-publish, research_vault catalog,
# immune journals, live quotes). The old loop had a 70-second total backoff window
# (sleep 7,14,21,28 across 5 attempts) and spent the CONFLICT remedy on it — a
# `git rebase --abort` plus a growing sleep — when all the race ever needed was one
# more re-sync-and-push. Capacity, not correctness.
#
# So this policy does two things the old loop could not:
#
#   1. It tells the two failure modes apart and spends the right remedy on each.
#      CONTENTION (ref-lock loss / non-fast-forward) retries FAST: the ref frees within
#      seconds and the whole job is to land in one of main's gaps. A real REBASE
#      CONFLICT backs off HARD, so main settles before the next replay — and it is
#      logged as a conflict, so a recurring one is visible as a NEW deterministic
#      conflict class rather than being buried in "lost a race".
#
#   2. It gives the loop a budget that matches main's actual commit rate: 10 attempts
#      inside a wall-clock deadline, with JITTERED sleeps. Jitter is load-bearing —
#      render.yml, engine-render.yml, closing-bell.yml and the nightly all retried on
#      the identical deterministic `sleep $((i * 7))` ladder, so two lanes that
#      collided once collided again on every single retry.
#
# The deadline is a HARD ceiling: no loop can outlive its job's timeout-minutes waiting
# for a ref. When it expires the caller's existing give-up path runs unchanged. Nothing
# here changes the caller's completion gate, `-X theirs` semantics, or
# scripts/rebase_autoresolve_hashed_css.sh. Render invokes this library only after its
# builders and guards complete, so an incomplete tree never enters the push loop.
#
# Tunables (plain shell assignments, set BEFORE push_retry_init — the library is
# SOURCED into the step's own shell, so no export is needed; each has a working
# default):
#   PUSH_MAX_ATTEMPTS  attempts before giving up          (default 10)
#   PUSH_BUDGET_SECS   wall-clock ceiling for the loop    (default 420)
#   PUSH_ALARM         seconds for a perl-alarm-bounded   (default unset = unbounded)
#                      `git push`, matching the lanes that already alarm-bound their
#                      git network ops on macOS runners (no GNU timeout there)
#
# Every function returns 0 unless it is a loop condition, so sourcing into GitHub's
# `bash -e` shell is safe.
# ---------------------------------------------------------------------------

# Begin a retry loop. $1 = human label used in logs and the step summary.
push_retry_init() {
  PUSH_LABEL="${1:-push}"
  PUSH_MAX_ATTEMPTS="${PUSH_MAX_ATTEMPTS:-10}"
  PUSH_BUDGET_SECS="${PUSH_BUDGET_SECS:-420}"
  PUSH_ALARM="${PUSH_ALARM:-}"
  PUSH_ATTEMPT=0
  PUSH_DEADLINE=$(( $(date +%s) + PUSH_BUDGET_SECS ))
  PUSH_N_CONTENTION=0
  PUSH_N_CONFLICT=0
  PUSH_N_OTHER=0
  PUSH_FAIL_CLASS=""
  PUSH_STOP=""
  return 0
}

# Loop condition. Returns 0 while another attempt is allowed, 1 once the attempt count
# or the wall-clock deadline is spent (PUSH_STOP records which). The FIRST attempt is
# always allowed regardless of the deadline.
push_attempt() {
  if [ "${PUSH_ATTEMPT}" -ge "${PUSH_MAX_ATTEMPTS}" ]; then
    PUSH_STOP="attempt budget exhausted (${PUSH_MAX_ATTEMPTS} attempts)"
    return 1
  fi
  if [ "${PUSH_ATTEMPT}" -gt 0 ] && [ "$(date +%s)" -ge "${PUSH_DEADLINE}" ]; then
    PUSH_STOP="time budget exhausted (${PUSH_BUDGET_SECS}s) after ${PUSH_ATTEMPT} attempts"
    return 1
  fi
  PUSH_ATTEMPT=$(( PUSH_ATTEMPT + 1 ))
  # Default for this attempt: it died on the fetch/rebase leg before ever reaching the
  # push. push_do and push_abort_rebase refine it from there.
  PUSH_FAIL_CLASS="sync"
  return 0
}

# Classify a failed `git push` from its exit code + combined output.
# Pure (no git calls) so tests can drive the table directly.
push_classify() {
  local rc="$1" out="$2"
  if [ "$rc" -eq 142 ]; then
    PUSH_FAIL_CLASS="push-timeout"
    return 0
  fi
  case "$out" in
    # A ref-lock loss is the signature contention failure: the remote ref moved between
    # our rebase and our push. No conflict happened; the replay is still good.
    *"cannot lock ref"*|*"failed to lock"*|*"Unable to create"*".lock"* )
      PUSH_FAIL_CLASS="contention" ;;
    # Same family: main advanced, so our push is no longer a fast-forward.
    *"fetch first"*|*"non-fast-forward"*|*"stale info"*|*"Updates were rejected"* )
      PUSH_FAIL_CLASS="contention" ;;
    # Anything else (auth, protected branch, a pre-receive hook) is NOT a race — back
    # off on the slow ladder and let the log show why.
    * )
      PUSH_FAIL_CLASS="push-error" ;;
  esac
  return 0
}

# `git push` with classification. Extra args are passed through. Returns push's status.
push_do() {
  local out rc=0
  if [ -n "${PUSH_ALARM}" ]; then
    out=$(perl -e 'alarm shift @ARGV; exec @ARGV or die' -- "${PUSH_ALARM}" git push "$@" 2>&1) || rc=$?
  else
    out=$(git push "$@" 2>&1) || rc=$?
  fi
  [ -z "$out" ] || printf '%s\n' "$out"
  if [ "$rc" -eq 0 ]; then
    PUSH_FAIL_CLASS=""
    return 0
  fi
  push_classify "$rc" "$out"
  return "$rc"
}

# Drop-in replacement for the loops' bare `git rebase --abort 2>/dev/null || true`.
# A rebase left IN PROGRESS is the tell for a real conflict — that is the one case that
# deserves the conflict remedy and the long backoff, so record it before aborting.
push_abort_rebase() {
  local gd=""
  gd=$(git rev-parse --git-dir 2>/dev/null) || gd=""
  if [ -n "$gd" ] && { [ -d "$gd/rebase-merge" ] || [ -d "$gd/rebase-apply" ]; }; then
    PUSH_FAIL_CLASS="rebase-conflict"
    git rebase --abort 2>/dev/null || true
  fi
  return 0
}

# One-line plain-word reason for the current class (used in the retry log line).
push_why() {
  case "${PUSH_FAIL_CLASS}" in
    contention)      printf '%s' "lost the race for refs/heads/main — no conflict, just retry" ;;
    rebase-conflict) printf '%s' "real rebase conflict — replay aborted, letting main settle" ;;
    push-timeout)    printf '%s' "push exceeded the ${PUSH_ALARM}s alarm" ;;
    push-error)      printf '%s' "push rejected for a non-contention reason — see the output above" ;;
    *)               printf '%s' "fetch/rebase leg failed before the push" ;;
  esac
  return 0
}

# Sleep before the next attempt, on a jittered ladder chosen by failure class, clamped
# to whatever is left of the wall-clock budget.
push_backoff() {
  local base cap secs left now
  case "${PUSH_FAIL_CLASS}" in
    contention)
      # The ref frees in seconds. Retry fast and often — the point is to win a gap.
      PUSH_N_CONTENTION=$(( PUSH_N_CONTENTION + 1 ))
      cap=20; base=$(( 2 + 3 * PUSH_ATTEMPT )) ;;
    rebase-conflict)
      # A conflict needs main to settle, not a faster retry.
      PUSH_N_CONFLICT=$(( PUSH_N_CONFLICT + 1 ))
      cap=60; base=$(( 8 * PUSH_ATTEMPT )) ;;
    *)
      PUSH_N_OTHER=$(( PUSH_N_OTHER + 1 ))
      cap=45; base=$(( 5 * PUSH_ATTEMPT )) ;;
  esac
  if [ "$base" -gt "$cap" ]; then base="$cap"; fi
  if [ "$base" -lt 2 ]; then base=2; fi
  # Full jitter over [base/2, base + base/2]. Load-bearing: the old deterministic
  # `sleep $((i * 7))` ladder made colliding lanes collide again on every retry.
  secs=$(( base / 2 + RANDOM % (base + 1) ))
  now=$(date +%s)
  left=$(( PUSH_DEADLINE - now ))
  if [ "$left" -lt 0 ]; then left=0; fi
  if [ "$secs" -gt "$left" ]; then secs="$left"; fi
  echo "${PUSH_LABEL} push attempt ${PUSH_ATTEMPT}/${PUSH_MAX_ATTEMPTS} failed [${PUSH_FAIL_CLASS}] — $(push_why); re-syncing in ${secs}s (${left}s of budget left)"
  if [ "$secs" -gt 0 ]; then sleep "$secs"; fi
  return 0
}

# Step-summary line. Emitted on every give-up, and on a win that needed a retry — so
# contention becomes VISIBLE instead of silent, without spamming the summary on the
# common first-attempt win.
push_summary() {
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
  printf -- '- push-retry · **%s**: %s · attempts=%s/%s · ref-lock losses=%s · rebase conflicts=%s · other=%s\n' \
    "${PUSH_LABEL}" "$1" "${PUSH_ATTEMPT}" "${PUSH_MAX_ATTEMPTS}" \
    "${PUSH_N_CONTENTION}" "${PUSH_N_CONFLICT}" "${PUSH_N_OTHER}" \
    >> "${GITHUB_STEP_SUMMARY}" 2>/dev/null || true
  return 0
}

push_won() {
  if [ "${PUSH_ATTEMPT}" -gt 1 ]; then push_summary "pushed"; fi
  return 0
}

push_lost() {
  # No-op unless the loop actually ran out of budget. Only push_attempt sets PUSH_STOP,
  # so a loop that left on a WIN never claims a loss — asia-close's data commit exits
  # its loop with `break` (it sits inside an if/else) and so runs the give-up tail on
  # the success path too. Guarding here keeps every call site safe.
  [ -n "${PUSH_STOP}" ] || return 0
  push_summary "NOT pushed — ${PUSH_STOP}"
  return 0
}
