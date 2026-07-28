#!/usr/bin/env bash
# Install the pinned Codex CLI used by the shared Claude OAuth + Codex provider
# pool. Authentication is intentionally separate: run
#
#   CODEX_HOME=/var/lib/macro-codex codex login --device-auth
#
# once on the VPS so it receives its own refreshable account session.
set -euo pipefail

CODEX_CLI_VERSION="${CODEX_CLI_VERSION:-0.145.0}"
CODEX_STATE_DIR="${CODEX_STATE_DIR:-/var/lib/macro-codex}"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

log() {
	[ "$QUIET" -eq 1 ] || echo "[codex-runtime] $*"
}

install -d -m 0700 "$CODEX_STATE_DIR"

CURRENT=""
if command -v codex >/dev/null 2>&1; then
	CURRENT=$(codex --version 2>/dev/null | awk '{print $2}' || true)
fi

if [ "$CURRENT" != "$CODEX_CLI_VERSION" ]; then
	log "installing @openai/codex@$CODEX_CLI_VERSION"
	if ! command -v npm >/dev/null 2>&1; then
		export DEBIAN_FRONTEND=noninteractive
		apt-get update -qq
		apt-get install -y nodejs npm >/dev/null
	fi
	npm install --global "@openai/codex@$CODEX_CLI_VERSION"
	CURRENT=$(codex --version 2>/dev/null | awk '{print $2}' || true)
	[ "$CURRENT" = "$CODEX_CLI_VERSION" ] || {
		echo "[codex-runtime] installed version mismatch: expected $CODEX_CLI_VERSION, got ${CURRENT:-absent}" >&2
		exit 1
	}
fi

if [ -f "$CODEX_STATE_DIR/auth.json" ]; then
	if CODEX_HOME="$CODEX_STATE_DIR" codex login status >/dev/null 2>&1; then
		log "ready: codex $CURRENT, dedicated VPS login present"
	else
		log "warning: auth.json exists but Codex reports no valid login"
	fi
else
	log "runtime ready; device login still required"
fi
