#!/bin/bash
# Create/refresh the TCC-safe earnings worker appliance and install its user
# LaunchAgent. This script intentionally contains paths and variable NAMES only;
# it never copies, prints, or inlines secret values.
set -euo pipefail

OPS_ROOT="${EARNINGS_OPS_ROOT:-/Users/chriswong/earnings-ops-wt}"
VENV_ROOT="${EARNINGS_VENV_ROOT:-/Users/chriswong/earnings-venv}"
REMOTE_URL="${EARNINGS_REMOTE_URL:-https://github.com/chriswong6031-creator/macro.git}"
ENV_FILE="${EARNINGS_ENV_FILE:-/Users/chriswong/flow-ops-wt/.env}"
DEST_DIR="${EARNINGS_LAUNCHAGENT_DIR:-$HOME/Library/LaunchAgents}"
LABEL="com.mastermind.earnings-worker"
DEST_PLIST="$DEST_DIR/$LABEL.plist"
DOMAIN="gui/$(/usr/bin/id -u)"
CHECK_ONLY=0
RUN_NOW=0
BOOTSTRAP_SINCE=""

usage() {
  cat <<'EOF'
Usage: bootstrap_earnings_worker.sh [--check] [--run-now]
                                    [--bootstrap-since YYYY-MM-DD]

  (no flags)                 create/refresh clone + venv and install LaunchAgent;
                             first scheduled run seeds forward-only
  --check                    validate an existing installation without mutation
  --run-now                  install, then kick one forward-only run
  --bootstrap-since DATE     before install, score one explicit recent slice;
                             allowed only when no intake cursor exists
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --run-now) RUN_NOW=1 ;;
    --bootstrap-since)
      [ "$#" -ge 2 ] || { echo "ERROR: --bootstrap-since needs YYYY-MM-DD" >&2; exit 2; }
      BOOTSTRAP_SINCE="$2"
      shift
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$CHECK_ONLY" -eq 1 ] && { [ "$RUN_NOW" -eq 1 ] || [ -n "$BOOTSTRAP_SINCE" ]; }; then
  echo "ERROR: --check cannot be combined with a run option" >&2
  exit 2
fi
if [ "$RUN_NOW" -eq 1 ] && [ -n "$BOOTSTRAP_SINCE" ]; then
  echo "ERROR: choose --run-now or --bootstrap-since, not both" >&2
  exit 2
fi
if [ -n "$BOOTSTRAP_SINCE" ] && ! [[ "$BOOTSTRAP_SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: --bootstrap-since must be YYYY-MM-DD" >&2
  exit 2
fi
case "$OPS_ROOT:$VENV_ROOT" in
  *"$HOME/Documents"*)
    echo "ERROR: earnings clone and venv must live outside ~/Documents" >&2
    exit 1
    ;;
esac

validate_clone() {
  [ -d "$OPS_ROOT/.git" ] || { echo "ERROR: missing standalone clone at $OPS_ROOT" >&2; return 1; }
  local top gitdir branch origin
  top="$(/usr/bin/git -C "$OPS_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
  gitdir="$(/usr/bin/git -C "$OPS_ROOT" rev-parse --absolute-git-dir 2>/dev/null || true)"
  branch="$(/usr/bin/git -C "$OPS_ROOT" symbolic-ref --quiet --short HEAD || true)"
  origin="$(/usr/bin/git -C "$OPS_ROOT" remote get-url origin 2>/dev/null || true)"
  [ "$top" = "$OPS_ROOT" ] && [ "$gitdir" = "$OPS_ROOT/.git" ] \
    || { echo "ERROR: $OPS_ROOT is not a standalone clone" >&2; return 1; }
  [ "$branch" = "main" ] \
    || { echo "ERROR: $OPS_ROOT must be on main (found ${branch:-detached})" >&2; return 1; }
  [ "$origin" = "$REMOTE_URL" ] \
    || { echo "ERROR: $OPS_ROOT origin is not the pinned macro remote" >&2; return 1; }
  [ -z "$(/usr/bin/git -C "$OPS_ROOT" status --porcelain --untracked-files=all)" ] \
    || { echo "ERROR: $OPS_ROOT is dirty; refusing to mutate it" >&2; return 1; }
}

if [ "$CHECK_ONLY" -eq 0 ] && [ ! -e "$OPS_ROOT" ]; then
  /usr/bin/git clone --filter=blob:none --sparse --branch main --single-branch \
    "$REMOTE_URL" "$OPS_ROOT"
  /usr/bin/git -C "$OPS_ROOT" sparse-checkout set engine lib scripts tools/earnings_worker config ops
fi
validate_clone

if [ "$CHECK_ONLY" -eq 0 ]; then
  /usr/bin/git -C "$OPS_ROOT" fetch origin main --quiet
  /usr/bin/git -C "$OPS_ROOT" merge --ff-only --quiet origin/main
  LOCAL_HEAD="$(/usr/bin/git -C "$OPS_ROOT" rev-parse HEAD)"
  REMOTE_HEAD="$(/usr/bin/git -C "$OPS_ROOT" rev-parse origin/main)"
  [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ] || {
    echo "ERROR: $OPS_ROOT is not exactly at origin/main after ff-only update" >&2
    exit 1
  }
fi

PLIST="$OPS_ROOT/ops/launchd/$LABEL.plist"
RUNNER="$OPS_ROOT/ops/launchd/run_earnings_worker.sh"
ENV_WRAPPER="$OPS_ROOT/ops/launchd/run_with_env.sh"
REQ="$OPS_ROOT/ops/earnings_worker_requirements.txt"
for path in "$PLIST" "$RUNNER" "$ENV_WRAPPER" "$REQ"; do
  [ -f "$path" ] || {
    echo "ERROR: origin/main does not yet contain required earnings ops file: $path" >&2
    echo "Wait for the producer/consumer PRs to merge before installing." >&2
    exit 1
  }
done
[ -f "$ENV_FILE" ] || { echo "ERROR: missing environment file: $ENV_FILE" >&2; exit 1; }
/usr/bin/plutil -lint "$PLIST" >/dev/null

if [ "$CHECK_ONLY" -eq 0 ]; then
  BOOTSTRAP_PYTHON="${EARNINGS_BOOTSTRAP_PYTHON:-/opt/homebrew/Caskroom/miniconda/base/bin/python}"
  if [ ! -x "$BOOTSTRAP_PYTHON" ]; then
    BOOTSTRAP_PYTHON="$(/usr/bin/which python3 2>/dev/null || true)"
  fi
  [ -x "$BOOTSTRAP_PYTHON" ] || { echo "ERROR: Python 3 is unavailable" >&2; exit 1; }
  if [ ! -x "$VENV_ROOT/bin/python" ]; then
    "$BOOTSTRAP_PYTHON" -m venv "$VENV_ROOT"
  fi
  REQ_SHA="$(/usr/bin/shasum -a 256 "$REQ" | /usr/bin/awk '{print $1}')"
  STAMP="$VENV_ROOT/.earnings-requirements.sha256"
  if [ "$(/bin/cat "$STAMP" 2>/dev/null || true)" != "$REQ_SHA" ]; then
    "$VENV_ROOT/bin/python" -m pip install --disable-pip-version-check -r "$REQ"
    printf '%s\n' "$REQ_SHA" > "$STAMP"
  fi
fi

[ -x "$VENV_ROOT/bin/python" ] || { echo "ERROR: missing dedicated venv at $VENV_ROOT" >&2; exit 1; }
"$VENV_ROOT/bin/python" -c 'import anthropic, boto3, pandas, pyarrow, requests, yaml'

# The wrapper is the only secret-loading seam. The runner reports only variable
# names and presence/absence, never their contents.
EARNINGS_PYTHON="$VENV_ROOT/bin/python" \
  "$ENV_WRAPPER" "$ENV_FILE" "$RUNNER" --check-env

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "OK: earnings appliance clone, venv, plist, and environment names validated"
  exit 0
fi

if [ -n "$BOOTSTRAP_SINCE" ]; then
  STATE="$OPS_ROOT/data/earnings_calls/terminal_intake_state.json"
  if [ -e "$STATE" ]; then
    echo "ERROR: explicit catch-up requires a new cursor; refusing to alter existing $STATE" >&2
    exit 1
  fi
  EARNINGS_PYTHON="$VENV_ROOT/bin/python" \
    "$ENV_WRAPPER" "$ENV_FILE" "$RUNNER" --bootstrap-since "$BOOTSTRAP_SINCE"
fi

/bin/mkdir -p "$DEST_DIR"
TMP_PLIST="$(/usr/bin/mktemp "$DEST_DIR/.$LABEL.XXXXXX")"
trap '/bin/rm -f "$TMP_PLIST"' EXIT
/usr/bin/install -m 0644 "$PLIST" "$TMP_PLIST"
/bin/mv "$TMP_PLIST" "$DEST_PLIST"

/bin/launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "$DOMAIN" "$DEST_PLIST"
/bin/launchctl enable "$DOMAIN/$LABEL"
if [ "$RUN_NOW" -eq 1 ]; then
  /bin/launchctl kickstart -k "$DOMAIN/$LABEL"
fi

echo "Installed $LABEL from $PLIST"
echo "Code: $OPS_ROOT"
echo "Python: $VENV_ROOT/bin/python"
echo "State: $OPS_ROOT/data/earnings_calls/terminal_intake_state.json (gitignored)"
echo "Log: /tmp/mm_earnings_worker.log"
