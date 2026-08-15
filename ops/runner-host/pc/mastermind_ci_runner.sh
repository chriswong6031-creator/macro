#!/bin/bash
set -euo pipefail

runner_root=${1:?runner root is required}
if [ -f "$runner_root/.path" ]; then
  export PATH
  PATH=$(cat "$runner_root/.path")
fi
if [ -f "$runner_root/.env" ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      ''|*[!A-Za-z0-9_]*) continue ;;
    esac
    export "$key=$value"
  done < "$runner_root/.env"
fi
export ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/libexec/mastermind-ci-admission-pc-ci.js
export MASTERMIND_CI_PROFILE=pc-ci
export MASTERMIND_CI_RUNNER_ROOT="$runner_root"
export HOME="$runner_root/_work/_home"
/usr/bin/python3 -I /usr/local/libexec/runner_cleanup.py --runner-root "$runner_root"
cd "$runner_root"
exec "$runner_root/bin/Runner.Listener" run --startuptype service --once
