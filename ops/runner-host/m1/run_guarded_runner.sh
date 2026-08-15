#!/bin/bash
set -euo pipefail

runner_root=${1:?runner root is required}
guard_root=${2:?guard root is required}

if ! "$guard_root/runner_disk_guard.py" --path "$runner_root" --mode lightweight; then
  # Disk pressure must not become a tight launchd crash loop. The listener remains
  # absent while this bounded backoff runs; launchd can retry after the host recovers.
  sleep 900
  exit 75
fi

"$guard_root/runner_log_maintenance.py" --diag "$runner_root/_diag"

# launchd, not the runner's nested Node service wrapper, owns restart semantics.
# Keeping Runner.Listener as the plist's final process makes a controlled listener
# crash observable as one launchd run transition instead of an invisible child retry.
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
cd "$runner_root"
exec "$runner_root/bin/Runner.Listener" run --startuptype service
