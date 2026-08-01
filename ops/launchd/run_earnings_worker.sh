#!/bin/bash
# Durable, launchd-safe producer for the earnings qualitative overlay.
#
# The code clone is immutable appliance code. Mutable cursor/parquet state lives
# under its already-gitignored data/earnings_calls/ directory and is transported
# through R2 by tools/earnings_worker/run_worker.py. Secrets are deliberately not
# read here: the LaunchAgent invokes this through run_with_env.sh and points that
# wrapper at /Users/chriswong/flow-ops-wt/.env.
set -euo pipefail

OPS_ROOT="${EARNINGS_OPS_ROOT:-/Users/chriswong/earnings-ops-wt}"
PYTHON="${EARNINGS_PYTHON:-/Users/chriswong/earnings-venv/bin/python}"
REMOTE_URL="${EARNINGS_REMOTE_URL:-https://github.com/chriswong6031-creator/macro.git}"
PROVIDER_ORDER="${EARNINGS_PROVIDER_ORDER:-deepseek}"
RUNTIME_ROOT="${EARNINGS_RUNTIME_ROOT:-/Users/chriswong/earnings-runtime}"
LOCK_DIR="${EARNINGS_LOCK_DIR:-/tmp/mm_earnings_worker.lock}"
POST_UPDATE=0
LOCK_HELD=0
CHECK_ENV=0
BOOTSTRAP_SINCE=""

ts() { /bin/date "+%Y-%m-%dT%H:%M:%S%z"; }

usage() {
  cat <<'EOF'
Usage: run_earnings_worker.sh [--check-env] [--bootstrap-since YYYY-MM-DD]

  --check-env                  verify required variable names, without values
  --bootstrap-since DATE       first-run-only, explicit bounded catch-up

Internal flags --post-update and --lock-held are reserved for the self-update
exec hop. Normal scheduled runs pass no arguments and seed forward-only on the
first invocation.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-env) CHECK_ENV=1 ;;
    --bootstrap-since)
      [ "$#" -ge 2 ] || { echo "ERROR: --bootstrap-since needs YYYY-MM-DD" >&2; exit 2; }
      BOOTSTRAP_SINCE="$2"
      shift
      ;;
    --post-update) POST_UPDATE=1 ;;
    --lock-held) LOCK_HELD=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -n "$BOOTSTRAP_SINCE" ] && ! [[ "$BOOTSTRAP_SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: --bootstrap-since must be YYYY-MM-DD" >&2
  exit 2
fi

verify_env_names() {
  local names=(R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET)
  local provider
  IFS=',' read -r -a providers <<< "$PROVIDER_ORDER"
  for provider in "${providers[@]}"; do
    case "${provider//[[:space:]]/}" in
      deepseek) names+=(DEEPSEEK_API_KEY) ;;
      kimi) names+=(MOONSHOT_API_KEY) ;;
      anthropic) names+=(ANTHROPIC_API_KEY) ;;
      codex) ;; # attached Codex login; availability is resolved at call time
      openai_compat|"") ;;
      *) echo "ERROR: unsupported provider name: $provider" >&2; return 1 ;;
    esac
  done

  local missing=()
  local name
  for name in "${names[@]}"; do
    if [ -z "${!name:-}" ]; then
      missing+=("$name")
    fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "ERROR: missing required environment variable name(s): ${missing[*]}" >&2
    return 1
  fi
  echo "OK: required environment variable names are present: ${names[*]}"
}

verify_env_names

canonical_path() {
  /usr/bin/python3 -c \
    'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve(strict=False))' \
    "$1"
}

is_within() {
  case "$1" in
    "$2"|"$2"/*) return 0 ;;
    *) return 1 ;;
  esac
}

case "$OPS_ROOT" in
  /*) ;;
  *) echo "ERROR: EARNINGS_OPS_ROOT must be an absolute path: $OPS_ROOT" >&2; exit 1 ;;
esac
OPS_ROOT="$(canonical_path "$OPS_ROOT")" || {
  echo "ERROR: could not canonicalize EARNINGS_OPS_ROOT" >&2
  exit 1
}
HOME_ROOT="$(canonical_path "$HOME")"
DOCUMENTS_ROOT="$(canonical_path "$HOME/Documents")"
if [ "$OPS_ROOT" = "/" ] || [ "$OPS_ROOT" = "$HOME_ROOT" ]; then
  echo "ERROR: EARNINGS_OPS_ROOT is too broad: $OPS_ROOT" >&2
  exit 1
fi
if is_within "$OPS_ROOT" "$DOCUMENTS_ROOT"; then
  echo "ERROR: EARNINGS_OPS_ROOT must live outside ~/Documents: $OPS_ROOT" >&2
  exit 1
fi

validate_state_root() {
  local label="$1"
  local raw="$2"
  local canonical
  case "$raw" in
    /*) ;;
    *) echo "ERROR: $label must be an absolute path: $raw" >&2; return 1 ;;
  esac
  canonical="$(canonical_path "$raw")" || {
    echo "ERROR: could not canonicalize $label" >&2
    return 1
  }
  if [ "$canonical" = "/" ] || [ "$canonical" = "$HOME_ROOT" ]; then
    echo "ERROR: $label is too broad: $canonical" >&2
    return 1
  fi
  if is_within "$canonical" "$OPS_ROOT"; then
    echo "ERROR: $label must live outside the immutable code clone: $canonical" >&2
    return 1
  fi
  if is_within "$canonical" "$DOCUMENTS_ROOT"; then
    echo "ERROR: $label must live outside ~/Documents: $canonical" >&2
    return 1
  fi
  printf '%s\n' "$canonical"
}

RUNTIME_ROOT="$(validate_state_root EARNINGS_RUNTIME_ROOT "$RUNTIME_ROOT")" || exit 1

# AI authentication records cost and quota telemetry as a side effect. Keep
# those append-only ledgers outside the fast-forward-only code appliance so a
# successful model call can never dirty the clone and block its next run.
AI_COSTS_STATE_ROOT="$(validate_state_root AI_COSTS_STATE_ROOT "${AI_COSTS_STATE_ROOT:-$RUNTIME_ROOT}")" || exit 1
METABOLISM_STATE_ROOT="$(validate_state_root METABOLISM_STATE_ROOT "${METABOLISM_STATE_ROOT:-$RUNTIME_ROOT}")" || exit 1
export AI_COSTS_STATE_ROOT METABOLISM_STATE_ROOT
STATE_PATH="$OPS_ROOT/data/earnings_calls/terminal_intake_state.json"
RUNNER="$OPS_ROOT/ops/launchd/run_earnings_worker.sh"

if [ "$CHECK_ENV" -eq 1 ]; then
  exit 0
fi

if [ ! -d "$OPS_ROOT/.git" ]; then
  echo "ERROR: missing standalone earnings ops clone at $OPS_ROOT" >&2
  echo "Run ops/bootstrap_earnings_worker.sh after the earnings PRs merge." >&2
  exit 1
fi
TOPLEVEL="$(/usr/bin/git -C "$OPS_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
GITDIR="$(/usr/bin/git -C "$OPS_ROOT" rev-parse --absolute-git-dir 2>/dev/null || true)"
BRANCH="$(/usr/bin/git -C "$OPS_ROOT" symbolic-ref --quiet --short HEAD || true)"
ORIGIN="$(/usr/bin/git -C "$OPS_ROOT" remote get-url origin 2>/dev/null || true)"
if [ "$TOPLEVEL" != "$OPS_ROOT" ] || [ "$GITDIR" != "$OPS_ROOT/.git" ]; then
  echo "ERROR: $OPS_ROOT is not a standalone clone" >&2
  exit 1
fi
if [ "$BRANCH" != "main" ]; then
  echo "ERROR: earnings ops clone must be on main (found ${BRANCH:-detached})" >&2
  exit 1
fi
if [ "$ORIGIN" != "$REMOTE_URL" ]; then
  echo "ERROR: earnings ops origin does not match the pinned macro remote" >&2
  exit 1
fi
if [ -n "$(/usr/bin/git -C "$OPS_ROOT" status --porcelain --untracked-files=all)" ]; then
  echo "ERROR: earnings ops clone is dirty; refusing self-update or scoring" >&2
  exit 1
fi
if [ ! -x "$PYTHON" ]; then
  echo "ERROR: missing dedicated earnings Python at $PYTHON" >&2
  exit 1
fi

# launchd serializes one label, but a manual kick may overlap a scheduled run.
# Reclaim only a lock whose owner PID is no longer alive.
if [ "$LOCK_HELD" -eq 0 ]; then
  if ! /bin/mkdir "$LOCK_DIR" 2>/dev/null; then
    LOCK_PID="$(/bin/cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [ -n "$LOCK_PID" ] && /bin/kill -0 "$LOCK_PID" 2>/dev/null; then
      echo "[$(ts)] SKIP: earnings worker PID $LOCK_PID holds $LOCK_DIR"
      exit 0
    fi
    /bin/rm -f "$LOCK_DIR/pid" 2>/dev/null || true
    /bin/rmdir "$LOCK_DIR" 2>/dev/null || true
    /bin/mkdir "$LOCK_DIR" 2>/dev/null || {
      echo "ERROR: could not reclaim stale lock $LOCK_DIR" >&2
      exit 1
    }
  fi
  echo "$$" > "$LOCK_DIR/pid"
elif [ "$(/bin/cat "$LOCK_DIR/pid" 2>/dev/null || true)" != "$$" ]; then
  echo "ERROR: inherited earnings lock ownership is invalid" >&2
  exit 1
fi

cleanup_lock() {
  /bin/rm -f "$LOCK_DIR/pid" 2>/dev/null || true
  /bin/rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Update while holding the lock, then exec the newly fetched runner exactly
# once. A local commit, divergence, dirty file, or non-ff update fails closed.
if [ "$POST_UPDATE" -eq 0 ]; then
  /usr/bin/git -C "$OPS_ROOT" fetch origin main --quiet
  /usr/bin/git -C "$OPS_ROOT" merge --ff-only --quiet origin/main
  LOCAL_HEAD="$(/usr/bin/git -C "$OPS_ROOT" rev-parse HEAD)"
  REMOTE_HEAD="$(/usr/bin/git -C "$OPS_ROOT" rev-parse origin/main)"
  if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
    echo "ERROR: earnings ops clone is not exactly at origin/main after ff-only update" >&2
    exit 1
  fi
  fresh_args=(--post-update --lock-held)
  if [ -n "$BOOTSTRAP_SINCE" ]; then
    fresh_args+=(--bootstrap-since "$BOOTSTRAP_SINCE")
  fi
  exec /bin/bash "$RUNNER" "${fresh_args[@]}"
fi

/bin/mkdir -p "$OPS_ROOT/data/earnings_calls"
if ! /usr/bin/git -C "$OPS_ROOT" check-ignore -q -- "$STATE_PATH"; then
  echo "ERROR: persistent earnings cursor is not covered by .gitignore: $STATE_PATH" >&2
  exit 1
fi

args=(
  "$OPS_ROOT/tools/earnings_worker/run_worker.py"
  --terminal-auto
  --limit 64
  --provider-order "$PROVIDER_ORDER"
  --repo-root "$OPS_ROOT"
  --terminal-state "$STATE_PATH"
)
if [ -n "$BOOTSTRAP_SINCE" ]; then
  args+=(--bootstrap-since "$BOOTSTRAP_SINCE")
fi

echo "[$(ts)] earnings worker start provider_order=$PROVIDER_ORDER"
"$PYTHON" "${args[@]}"
echo "[$(ts)] earnings worker complete"
