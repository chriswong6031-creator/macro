#!/bin/sh
# ops/launchd/run_with_env.sh — wrapper used by launchd plists to source .env
# before executing a Python module.
#
# Usage (from plist ProgramArguments):
#   /path/to/run_with_env.sh /path/to/.env python -m scripts.some_module [args...]
#
# The first argument is the .env file path; remaining arguments form the command.
# NEVER inline secrets in the plist EnvironmentVariables block — use this wrapper.
#
# The wrapper:
#   1. Sources the .env file with set -a so variables are exported.
#   2. Executes the remaining arguments as a command.
#
# If the .env file does not exist the command still runs (env vars may be set
# by other means, e.g. System Preferences or /etc/launchd.conf).

ENV_FILE="$1"
shift

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$ENV_FILE"
    set +a
fi

exec "$@"
