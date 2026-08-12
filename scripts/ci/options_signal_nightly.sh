#!/usr/bin/env bash
# shellcheck shell=bash
#
# Size-safe nightly publication policy for the options PIT episode and canonical
# campaign-v2 ledgers.  GitHub silently stops processing daily.yml near 512 KB,
# so the executable shell lives here while the workflow keeps the causal order,
# conditions, timeouts, and operator-facing rationale visible.
#
# Commands:
#   publish-episode   Publish exactly the five current episode-ledger files.
#                     Its candidate commit remains unreachable locally until
#                     origin/main accepts the metadata replay. A failure cannot
#                     let the broad engine commit smuggle episode output.
#   publish-campaign  Publish exactly the three canonical campaign-v2 files.
#                     Its candidate commit remains unreachable locally until
#                     origin/main accepts the metadata replay.  A failure cannot
#                     let the broad engine commit smuggle campaign-v2 output.
#   exclude-broad     After the broad `git add data/`, restore/reset all narrow
#                     paths and remove only campaign-v2 builder-owned additions.
#                     Both publishers leave HEAD unchanged, so all same-run narrow
#                     mutations are removed before the broad engine commit.
#   assert-integrity  Terminal fail-closed gate over all four workflow outcomes.

set -euo pipefail

REPO_ROOT="${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
# shellcheck source=scripts/ci/push_retry.sh
. "$REPO_ROOT/scripts/ci/push_retry.sh"

readonly -a OIP_EPISODE_PATHS=(
  data/options_signal_episode/checkpoint.json
  data/options_signal_episode/episodes.jsonl
  data/options_signal_episode/outcomes_h60.jsonl
  data/options_signal_episode/outcomes_session.jsonl
  data/options_signal_episode/campaigns.jsonl
)
readonly -a OIP_CAMPAIGN_PATHS=(
  data/options_signal_campaign/campaigns.jsonl
  data/options_signal_campaign/outcomes.jsonl
  data/options_signal_campaign/checkpoint.json
)

oip_require_clean_index() {
  local title="$1"
  if ! git diff --cached --quiet; then
    echo "::error title=${title} index dirty::foreign staged paths predate the narrow checkpoint; refusing to publish"
    return 1
  fi
}

oip_require_regular_files() {
  local title="$1"
  shift
  local path
  for path in "$@"; do
    if [ ! -f "$path" ] || [ -L "$path" ]; then
      echo "::error title=${title} path rejected::$path is missing or a symlink"
      return 1
    fi
  done
}

oip_require_exact_staged_paths() {
  local title="$1"
  shift
  local -a allowed=("$@")
  local path candidate matched scope_list
  scope_list=$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/oip-staged-scope.XXXXXX") || return 1
  if ! git diff --cached --name-only > "$scope_list"; then
    rm -f -- "$scope_list"
    echo "::error title=${title} scope enumeration failed::cannot enumerate the whole staged index; refusing to publish"
    return 1
  fi
  while IFS= read -r path; do
    matched=false
    for candidate in "${allowed[@]}"; do
      if [ "$path" = "$candidate" ]; then
        matched=true
        break
      fi
    done
    if [ "$matched" != true ]; then
      echo "::error title=${title} scope violation::staged path $path is outside the exact allowlist"
      rm -f -- "$scope_list"
      return 1
    fi
  done < "$scope_list"
  rm -f -- "$scope_list"
}

if ! declare -F oip_after_scope_check >/dev/null 2>&1; then
oip_after_scope_check() {
  # Test-only race hook: a subprocess may define this function after sourcing
  # the helper to mutate the live index at the exact former TOCTOU boundary.
  # Production executes this no-op. The candidate builder below must remain
  # isolated even if the hook stages a foreign path.
  return 0
}
fi

if ! declare -F oip_after_stage_snapshot >/dev/null 2>&1; then
oip_after_stage_snapshot() {
  # Test-only race hook at the boundary after the one-process allowed-entry
  # snapshot. Production is a no-op; tests re-stage every allowed path here to
  # prove the private candidate stays wholly on the frozen pre-race generation.
  return 0
}
fi

# Build a candidate commit from a caller-owned index seeded from HEAD. The live
# index is adversarial shared state: another process can stage a foreign path
# after the exact-scope check but before `git write-tree`. Reading the allowed
# paths' staged mode/OID entries once and overlaying only those entries into this
# private index makes that race an isolation event, never a scope escape.
oip_exact_candidate_commit() {
  local parent="$1" message="$2" index_path="$3"
  shift 3
  local -a allowed=("$@") seen=()
  local path stage_entry meta mode oid tree commit rc=0 snapshot_path

  rm -f -- "$index_path" "$index_path.lock"
  snapshot_path=$(mktemp "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/oip-stage-snapshot.XXXXXX") || return 1
  # One git process snapshots every allowed entry. Per-path invocations would let
  # a concurrent writer re-stage one allowed path between reads and create a
  # mixed-generation candidate even though no foreign path could enter it.
  if ! git ls-files --stage -- "${allowed[@]}" > "$snapshot_path"; then
    rm -f -- "$snapshot_path"
    echo "::error title=options candidate snapshot failed::cannot atomically enumerate the exact allowed index entries" >&2
    return 1
  fi
  oip_after_stage_snapshot
  GIT_INDEX_FILE="$index_path" git read-tree "$parent" || rc=$?
  while [ "$rc" -eq 0 ] && IFS= read -r stage_entry; do
    [ "$rc" -eq 0 ] || break
    if [ -z "$stage_entry" ] || [ "${stage_entry#*$'\t'}" = "$stage_entry" ]; then
      echo "::error title=options candidate index rejected::malformed staged entry in exact snapshot" >&2
      rc=1
      break
    fi
    path=${stage_entry#*$'\t'}
    meta=${stage_entry%%$'\t'*}
    mode=${meta%% *}
    meta=${meta#* }
    oid=${meta%% *}
    if [ "$mode" != 100644 ] || [ "${meta##* }" != 0 ]; then
      echo "::error title=options candidate index rejected::$path must be a stage-0 regular file with mode 100644" >&2
      rc=1
      break
    fi
    case " ${allowed[*]} " in
      *" $path "*) ;;
      *)
        echo "::error title=options candidate scope rejected::$path is not in the exact allowed set" >&2
        rc=1
        break
        ;;
    esac
    if [ "${#seen[@]}" -gt 0 ]; then
      case " ${seen[*]} " in
        *" $path "*)
          echo "::error title=options candidate duplicate rejected::$path appears more than once in the exact snapshot" >&2
          rc=1
          break
          ;;
      esac
    fi
    seen+=("$path")
    if ! git cat-file -e "$oid^{blob}" 2>/dev/null; then
      echo "::error title=options candidate object rejected::$path points to a missing or non-blob object" >&2
      rc=1
      break
    fi
    GIT_INDEX_FILE="$index_path" git update-index --add --cacheinfo \
      "$mode" "$oid" "$path" || rc=$?
  done < "$snapshot_path"
  if [ "$rc" -eq 0 ] && [ "${#seen[@]}" -ne "${#allowed[@]}" ]; then
    echo "::error title=options candidate path set rejected::expected ${#allowed[@]} exact entries, found ${#seen[@]}" >&2
    rc=1
  fi
  if [ "$rc" -eq 0 ]; then
    tree=$(GIT_INDEX_FILE="$index_path" git write-tree --missing-ok) || rc=$?
  fi
  if [ "$rc" -eq 0 ]; then
    commit=$(printf '%s\n' "$message" | git commit-tree "$tree" -p "$parent") || rc=$?
  fi
  rm -f -- "$index_path" "$index_path.lock" "$snapshot_path"
  [ "$rc" -eq 0 ] || return "$rc"
  printf '%s\n' "$commit"
}

oip_replay_and_push() {
  local parent="$1" candidate="$2" message="$3" replay_index="$4"
  local label="$5" success_subject="$6" fallback_message="$7"
  local publish=""

  while push_attempt; do
    if ! perl -e 'alarm 120; exec @ARGV or die' -- git fetch origin \
      +refs/heads/main:refs/remotes/origin/main; then
      PUSH_FAIL_CLASS="sync"
      push_backoff
      continue
    fi
    if publish=$(push_metadata_replay_commit \
        "$parent" origin/main "$candidate" "$message" "$replay_index"); then
      if [ "$(git rev-parse "$publish^{tree}")" = \
           "$(git rev-parse origin/main^{tree})" ]; then
        echo "$label content already on origin/main — nothing to push"
        push_won
        return 0
      fi
      if push_do origin "$publish:refs/heads/main"; then
        echo "pushed $success_subject on attempt $PUSH_ATTEMPT (metadata replay — dirty render tree untouched)"
        push_won
        return 0
      fi
    else
      PUSH_FAIL_CLASS="rebase-conflict"
    fi
    push_backoff
  done
  push_lost
  echo "::error title=${label} NOT pushed::$PUSH_ATTEMPT attempts failed ($PUSH_STOP); $fallback_message"
  return 1
}

publish_episode() {
  git config user.name "dashboard-bot"
  git config user.email "actions@users.noreply.github.com"
  PUSH_ALARM=120
  PUSH_BUDGET_SECS=420
  PUSH_MAX_ATTEMPTS=12
  push_retry_init "options PIT episode ledgers"
  push_on_main_ok || return 0

  oip_require_clean_index "options PIT checkpoint"
  oip_require_regular_files "options PIT checkpoint" "${OIP_EPISODE_PATHS[@]}"
  git add -- "${OIP_EPISODE_PATHS[@]}"
  if git diff --cached --quiet; then
    echo "options PIT episode ledgers unchanged"
    return 0
  fi
  oip_require_exact_staged_paths "options PIT checkpoint" "${OIP_EPISODE_PATHS[@]}"
  oip_after_scope_check
  push_staged_clean "${OIP_EPISODE_PATHS[@]}"

  local parent commit message candidate_index replay_index
  parent=$(git rev-parse 'HEAD^{commit}')
  message="options-pit: durable episode checkpoint $(date -u +%F)"
  # Keep the candidate unreachable until origin/main accepts it. A timeout or
  # cancellation therefore cannot leave a local commit for the later broad
  # publisher to smuggle before the terminal integrity gate runs.
  candidate_index="${RUNNER_TEMP:-/tmp}/options-pit-candidate-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.idx"
  commit=$(oip_exact_candidate_commit \
    "$parent" "$message" "$candidate_index" "${OIP_EPISODE_PATHS[@]}")
  git reset -q -- "${OIP_EPISODE_PATHS[@]}"
  replay_index="${RUNNER_TEMP:-/tmp}/options-pit-replay-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.idx"
  oip_replay_and_push \
    "$parent" "$commit" "$message" "$replay_index" \
    "options PIT checkpoint" \
    "options PIT episode ledgers" \
    "HEAD never advanced and the run will stay red"
}

publish_campaign() {
  git config user.name "dashboard-bot"
  git config user.email "actions@users.noreply.github.com"
  PUSH_ALARM=120
  PUSH_BUDGET_SECS=420
  PUSH_MAX_ATTEMPTS=12
  push_retry_init "options campaign v2 ledgers"
  push_on_main_ok || return 0

  oip_require_clean_index "options campaign checkpoint"
  oip_require_regular_files "options campaign checkpoint" "${OIP_CAMPAIGN_PATHS[@]}"
  git add -- "${OIP_CAMPAIGN_PATHS[@]}"
  if git diff --cached --quiet; then
    echo "options campaign v2 ledgers unchanged"
    return 0
  fi
  oip_require_exact_staged_paths "options campaign checkpoint" "${OIP_CAMPAIGN_PATHS[@]}"
  oip_after_scope_check
  push_staged_clean "${OIP_CAMPAIGN_PATHS[@]}"

  local parent commit message candidate_index replay_index
  parent=$(git rev-parse 'HEAD^{commit}')
  message="options-campaign-v2: durable checkpoint $(date -u +%F)"
  # The campaign candidate remains unreachable until origin/main accepts it.
  # Timeout, cancellation, or push exhaustion therefore cannot advance HEAD or
  # create a commit that the later broad publisher could accidentally carry.
  candidate_index="${RUNNER_TEMP:-/tmp}/options-campaign-v2-candidate-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.idx"
  commit=$(oip_exact_candidate_commit \
    "$parent" "$message" "$candidate_index" "${OIP_CAMPAIGN_PATHS[@]}")
  git reset -q -- "${OIP_CAMPAIGN_PATHS[@]}"
  replay_index="${RUNNER_TEMP:-/tmp}/options-campaign-v2-replay-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.idx"
  oip_replay_and_push \
    "$parent" "$commit" "$message" "$replay_index" \
    "options campaign checkpoint" \
    "options campaign v2 ledgers" \
    "HEAD never advanced and the run will stay red"
}

exclude_broad() {
  local -a tracked=()
  local path
  for path in "${OIP_EPISODE_PATHS[@]}" "${OIP_CAMPAIGN_PATHS[@]}"; do
    if git cat-file -e "HEAD:$path" 2>/dev/null; then
      tracked+=("$path")
    fi
  done
  if [ "${#tracked[@]}" -gt 0 ]; then
    git checkout HEAD -- "${tracked[@]}"
  fi
  git reset -q -- "${OIP_EPISODE_PATHS[@]}" "${OIP_CAMPAIGN_PATHS[@]}"
  # This entire directory is owned by the campaign-v2 builder.  Cleaning the
  # precise root removes first-publication additions without touching the frozen
  # legacy v1 corpus in data/options_signal_episode/campaigns.jsonl.
  git clean -fd -- data/options_signal_campaign
}

assert_integrity() {
  if [ "${OIP_EPISODE_BUILD_OUTCOME:-}" = success ] && \
     [ "${OIP_EPISODE_PUBLISH_OUTCOME:-}" = success ] && \
     [ "${OIP_CAMPAIGN_BUILD_OUTCOME:-}" = success ] && \
     [ "${OIP_CAMPAIGN_PUBLISH_OUTCOME:-}" = success ]; then
    echo "OIP PIT integrity passed"
    return 0
  fi
  echo "::error title=OIP PIT integrity::episode/campaign build or narrow publication failed"
  return 1
}

if [ "${OIP_NIGHTLY_SOURCE_ONLY:-0}" != 1 ]; then
  case "${1:-}" in
    publish-episode) publish_episode ;;
    publish-campaign) publish_campaign ;;
    exclude-broad) exclude_broad ;;
    assert-integrity) assert_integrity ;;
    *)
      echo "usage: $0 {publish-episode|publish-campaign|exclude-broad|assert-integrity}" >&2
      exit 64
      ;;
  esac
fi
