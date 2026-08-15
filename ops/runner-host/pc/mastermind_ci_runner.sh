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
cd "$runner_root"
exec "$runner_root/bin/Runner.Listener" run --startuptype service
