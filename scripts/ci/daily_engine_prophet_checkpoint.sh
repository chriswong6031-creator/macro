#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `engine`, step `checkpoint Prophet outputs to main (durable before engine tail)`.
# 2026-08-26 512KB processing-cap headroom diet (tests/test_workflow_file_size.py;
# PR #6499 left ~36 bytes of headroom). Env comes from the step's `env:` block,
# which stays in the YAML.
# Invoked as: bash scripts/ci/daily_engine_prophet_checkpoint.sh
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

set -euo pipefail
. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"

# SOURCE authority fence. workflow_dispatch can be invoked on any
# ref; only a checkout actually on local main whose commit remains in
# origin/main history may publish generated artifacts to main. Exact
# equality is intentionally not required because this multi-hour job
# routinely sees unrelated main commits after checkout.
EVENT_REF="${GITHUB_REF:-}"
EVENT_SHA="${GITHUB_SHA:-}"
SOURCE_BRANCH="$(git -C "$GITHUB_WORKSPACE" symbolic-ref --short -q HEAD || true)"
SOURCE_HEAD="$(git -C "$GITHUB_WORKSPACE" rev-parse HEAD)"
git -C "$GITHUB_WORKSPACE" fetch origin \
  +refs/heads/main:refs/remotes/origin/main
if [ "$EVENT_REF" != "refs/heads/main" ] \
  || [ -z "$EVENT_SHA" ] \
  || [ "$SOURCE_BRANCH" != "main" ] \
  || ! git -C "$GITHUB_WORKSPACE" merge-base --is-ancestor \
    "$SOURCE_HEAD" origin/main; then
  echo "::error title=Prophet checkpoint source rejected::event ref=${EVENT_REF:-unset} sha=${EVENT_SHA:-unset}; source branch=${SOURCE_BRANCH:-detached} commit=$SOURCE_HEAD — event and checkout must both be origin/main ancestry; off-main workflow_dispatch output will not publish"
  exit 1
fi
if [ -z "${PROPHET_DELTA_MANIFEST:-}" ] \
  || [ ! -f "$PROPHET_DELTA_MANIFEST" ]; then
  echo "::error title=Prophet checkpoint manifest missing::successful build supplied no readable owned-output delta manifest"
  exit 1
fi
if [ ! -s "$PROPHET_DELTA_MANIFEST" ]; then
  echo "Prophet checkpoint: build produced no owned-output delta"
  exit 0
fi

CHECKPOINT_ROOT="$(mktemp -d "${RUNNER_TEMP}/prophet-checkpoint.XXXXXX")"
CHECKPOINT_DIR="${CHECKPOINT_ROOT}/tree"
CHECKPOINT_BRANCH="_prophet_checkpoint_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT:-1}"
cleanup_prophet_checkpoint() {
  cd "$GITHUB_WORKSPACE"
  git worktree remove --force "$CHECKPOINT_DIR" 2>/dev/null || true
  git branch -D "$CHECKPOINT_BRANCH" 2>/dev/null || true
  rmdir "$CHECKPOINT_ROOT" 2>/dev/null || true
}
trap cleanup_prophet_checkpoint EXIT

git worktree add -b "$CHECKPOINT_BRANCH" "$CHECKPOINT_DIR" origin/main

cd "$CHECKPOINT_DIR"
# A correction merged while this engine was running changes the
# effective plan/index projection. Refuse to publish an index derived
# from the older correction view, even though correction ledgers are
# themselves excluded from the output manifest.
PROTECTED_PROPHET_PATHS=(
  data/prophet/plan_corrections.jsonl
  data/prophet/ledger_corrections.jsonl
  data/prophet
  data/prophet_arena
  site/prophet
)
if ! git diff --quiet "$SOURCE_HEAD" origin/main -- \
  "${PROTECTED_PROPHET_PATHS[@]}"; then
  echo "::error title=Prophet checkpoint provenance race::origin/main Prophet publications or correction ledgers changed after the source checkout; preserving main and withholding the stale derived checkpoint"
  exit 1
fi

while IFS=$'\t' read -r rel before_sha after_sha; do
  [ -n "$rel" ] || continue
  case "/$rel/" in
    *"/../"*|*"/./"*|"//"*|*\\*)
      echo "::error title=Prophet checkpoint path rejected::manifest path $rel is not a normalized repository-relative path"
      exit 1
      ;;
  esac
  case "$rel" in
    site/prophet/index.json|site/prophet/showcase.json|\
    site/prophet/board_read_sparks.json|\
    data/prophet/ledger.jsonl|data/prophet/ledger_quarantine.json|\
    data/prophet_arena/scoreboard.json|\
    data/prophet/origination_receipts/*.json|\
    data/prophet/legacy_shadow/*/*.parquet|\
    data/prophet_arena/price_basis_trigger_v2/C0_champion_mirror.jsonl|\
    data/prophet_arena/price_basis_trigger_v2/C1_buy_soon_first.jsonl|\
    data/prophet_arena/price_basis_trigger_v2/C3_door_w_union.jsonl|\
    data/prophet_arena/price_basis_trigger_v2/C4_dispersion_cap.jsonl|\
    data/prophet_arena/price_basis_trigger_v2/C5_align2_gate.jsonl|\
    data/prophet_arena/price_basis_trigger_v2/C6_time_stop_21.jsonl|\
    data/prophet_arena/price_basis_trigger_v2/C7_buy_soon_admitted.jsonl|\
    site/prophet/plans/*.json|site/prophet/states/*.json\
    ) ;;
    *)
      echo "::error title=Prophet checkpoint path rejected::manifest path $rel is outside the closed build-owned allowlist"
      exit 1
      ;;
  esac
  if [ ! -f "$GITHUB_WORKSPACE/$rel" ]; then
    echo "::error title=Prophet checkpoint output missing::manifest path $rel no longer exists; deletions are forbidden"
    exit 1
  fi
  current_after="$(python3 -c 'import hashlib,os,sys; p=sys.argv[1]; mode=f"{os.stat(p).st_mode & 0o7777:04o}"; sha=hashlib.sha256(open(p,"rb").read()).hexdigest(); print(mode+":"+sha)' "$GITHUB_WORKSPACE/$rel")"
  if [ "$current_after" != "$after_sha" ]; then
    echo "::error title=Prophet checkpoint source changed::manifest path $rel changed after build completion; refusing an unproven snapshot"
    exit 1
  fi
  if [ -L "$CHECKPOINT_DIR/$rel" ]; then
    echo "::error title=Prophet checkpoint symlink rejected::origin/main path $rel is a symlink; refusing to follow it during publication"
    exit 1
  elif [ -f "$CHECKPOINT_DIR/$rel" ]; then
    main_before="$(python3 -c 'import hashlib,os,sys; p=sys.argv[1]; mode=f"{os.stat(p).st_mode & 0o7777:04o}"; sha=hashlib.sha256(open(p,"rb").read()).hexdigest(); print(mode+":"+sha)' "$CHECKPOINT_DIR/$rel")"
  else
    main_before="MISSING"
  fi
  if [ "$main_before" != "$before_sha" ]; then
    echo "::error title=Prophet checkpoint same-path race::origin/main changed $rel after this build's baseline; preserving main and withholding the checkpoint"
    exit 1
  fi
  mkdir -p "$CHECKPOINT_DIR/$(dirname "$rel")"
  cp -p "$GITHUB_WORKSPACE/$rel" "$CHECKPOINT_DIR/$rel"
  git add -- "$rel"
done < "$PROPHET_DELTA_MANIFEST"

if git diff --cached --quiet; then
  echo "Prophet checkpoint: no artifact changes"
  exit 0
fi
if ! push_staged_clean; then
  echo "::error title=Prophet checkpoint refused::conflict-marker guard rejected the narrow checkpoint"
  exit 1
fi
git commit -m "prophet-us: durable nightly checkpoint $(date -u +%F)"
CHECKPOINT_PARENT="$(git rev-parse HEAD^)"

# The checkpoint worktree is clean, so no --autostash is necessary.
# Each retry first proves that neither a correction input nor any
# manifest path changed on main. Only then may this narrow commit
# rebase over unrelated main commits — with no strategy override.
PUSH_ALARM=120
PUSH_BUDGET_SECS=420
PUSH_MAX_ATTEMPTS=12
PUSH_MAIN_BRANCHES="$CHECKPOINT_BRANCH"
push_retry_init "Prophet durable checkpoint"
push_on_main_ok || exit 0
while push_attempt; do
  if ! push_fetch_main_for_rebase; then
    push_abort_rebase
    push_backoff
    continue
  fi
  if ! git diff --quiet "$SOURCE_HEAD" origin/main -- \
    "${PROTECTED_PROPHET_PATHS[@]}"; then
    echo "::error title=Prophet checkpoint provenance race::origin/main Prophet publications or correction ledgers advanced during publish; preserving main and aborting"
    exit 1
  fi
  same_path=""
  while IFS=$'\t' read -r rel _ _; do
    [ -n "$rel" ] || continue
    if ! git diff --quiet "$CHECKPOINT_PARENT" origin/main -- "$rel"; then
      same_path="${same_path}${same_path:+, }${rel}"
    fi
  done < "$PROPHET_DELTA_MANIFEST"
  if [ -n "$same_path" ]; then
    echo "::error title=Prophet checkpoint same-path race::origin/main advanced build-owned path(s): $same_path; no merge strategy override is allowed, preserving main"
    exit 1
  fi
  if perl -e 'alarm 180; exec @ARGV or die' -- git rebase origin/main; then
    CHECKPOINT_PARENT="$(git rev-parse HEAD^)"
    if push_do origin HEAD:main; then
      echo "pushed Prophet durable checkpoint on attempt $PUSH_ATTEMPT"
      push_won
      # Arm R2 only after the guarded commit is confirmed in current
      # origin/main and no newer Prophet/correction write overtook it.
      # The publisher receives the SHA-256 proven by the build delta;
      # it reconstructs the bytes from this exact commit, never from
      # the dirty engine worktree.
      CHECKPOINT_SHA="$(git rev-parse HEAD)"
      if ! git fetch origin \
        +refs/heads/main:refs/remotes/origin/main; then
        echo "::error title=Prophet R2 arm withheld::checkpoint landed, but current origin/main could not be verified; R2 remains on its prior accepted object"
        exit 1
      fi
      if ! git merge-base --is-ancestor "$CHECKPOINT_SHA" origin/main \
        || ! git diff --quiet "$CHECKPOINT_SHA" origin/main -- \
          data/prophet \
          data/prophet_arena \
          site/prophet; then
        echo "::warning title=Prophet R2 arm superseded::origin/main advanced a Prophet publication or correction after checkpoint $CHECKPOINT_SHA; this older build will not write R2"
        exit 0
      fi
      INDEX_FINGERPRINT="$(awk -F '\t' '$1 == "site/prophet/index.json" { print $3 }' "$PROPHET_DELTA_MANIFEST")"
      if [ -z "$INDEX_FINGERPRINT" ]; then
        echo "::notice title=Prophet R2 no-op::the accepted checkpoint did not change site/prophet/index.json; no R2 write is needed"
        exit 0
      fi
      INDEX_SHA256="${INDEX_FINGERPRINT#*:}"
      CHECKPOINT_INDEX_SHA256="$(git show "${CHECKPOINT_SHA}:site/prophet/index.json" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
      if [ "$CHECKPOINT_INDEX_SHA256" != "$INDEX_SHA256" ]; then
        echo "::error title=Prophet R2 arm hash mismatch::checkpointed index bytes do not match the proven build delta; R2 publication withheld"
        exit 1
      fi
      echo "r2_ready=true" >> "$GITHUB_OUTPUT"
      echo "checkpoint_sha=$CHECKPOINT_SHA" >> "$GITHUB_OUTPUT"
      echo "index_sha256=$INDEX_SHA256" >> "$GITHUB_OUTPUT"
      exit 0
    fi
  fi
  push_abort_rebase
  push_backoff
done
push_lost
echo "::error title=Prophet checkpoint NOT pushed::$PUSH_ATTEMPT attempts failed ($PUSH_STOP); R2 remains on its prior accepted object, and the final engine commit is fenced from publishing this uncheckpointed Prophet tree"
exit 1
