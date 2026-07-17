#!/usr/bin/env bash
# scripts/run_theta_terminal.sh — launch the ThetaData Terminal v3 Java client.
#
# The Theta Terminal v3 is a local Java process that serves the ThetaData v3 REST API on
# http://127.0.0.1:25503.  It must be running before any collectors/thetadata.py call.
#
# v2 (ThetaTerminal.jar, port 25510) is DEAD — all /v2/* paths return HTTP 410 Gone.
# This script launches v3 (ThetaTerminalv3.jar, port 25503) only.
#
# Credentials (never echoed, never in argv):
#   - Primary: THETA_API_KEY environment variable
#   - Fallback: .env file at the repo root (KEY=VALUE format, one per line)
#   The key is handed to the terminal as the THETADATA_API_KEY environment variable
#   (supported natively by Terminal v3; lookup order there is CLI arg > env > jar-dir
#   .env).  NEVER pass it as the --api-key launch argument: argv is readable in
#   plaintext by every local process via `ps` (found live 2026-07-16).
#
# Jar location: ~/theta/ThetaTerminalv3.jar
#   If absent, instructions are printed.
#
# Java requirement: Java 21 (measured requirement — ThetaTerminalv3 requires JDK 21).
#   Install: brew install openjdk@21
#   The script sets JAVA_HOME to /opt/homebrew/opt/openjdk@21 if it exists and java is not 21.
#
# Health check endpoint (v3): GET http://127.0.0.1:25503/v3/option/list/symbols
#
# Usage:
#   scripts/run_theta_terminal.sh
#   THETA_API_KEY=your_key scripts/run_theta_terminal.sh

set -euo pipefail

THETA_DIR="$HOME/theta"
JAR_PATH="$THETA_DIR/ThetaTerminalv3.jar"
LOG_PATH="$THETA_DIR/terminal_v3.log"
HEALTH_URL="http://127.0.0.1:25503/v3/option/list/symbols"
MIN_JAVA_VERSION=21
REQUIRED_JAVA_HOME="/opt/homebrew/opt/openjdk@21"

# ── Credential resolution (never echo the key) ────────────────────────────────
_load_env() {
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    ENV_FILE="$REPO_ROOT/.env"
    if [[ -f "$ENV_FILE" ]]; then
        # Export KEY=VALUE lines that aren't comments; skip lines without '='
        set -o allexport
        # shellcheck disable=SC1090
        source <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | grep -v '^#')
        set +o allexport
    fi
}

_load_env

# THETA_API_KEY is read but never printed — exported to the JVM as THETADATA_API_KEY
THETA_KEY="${THETA_API_KEY:-}"

if [[ -z "$THETA_KEY" ]]; then
    echo "ERROR: THETA_API_KEY not set."
    echo ""
    echo "Set it in your environment:"
    echo "  export THETA_API_KEY=your_api_key"
    echo ""
    echo "Or add it to .env at the repo root:"
    echo "  THETA_API_KEY=your_api_key"
    echo ""
    echo "Find your API key at https://thetadata.us/account"
    exit 1
fi

# ── Java 21 check + JAVA_HOME setup ──────────────────────────────────────────
# ThetaTerminalv3 requires Java 21 exactly (measured 2026-07-04).
# If JAVA_HOME is already set to Java 21, use it; otherwise try the brew path.

if [[ -d "$REQUIRED_JAVA_HOME" ]]; then
    export JAVA_HOME="$REQUIRED_JAVA_HOME"
    export PATH="$JAVA_HOME/bin:$PATH"
fi

if ! command -v java &>/dev/null; then
    echo "ERROR: 'java' not found in PATH."
    echo ""
    echo "Install Java 21 via Homebrew:"
    echo "  brew install openjdk@21"
    echo "  export JAVA_HOME=/opt/homebrew/opt/openjdk@21"
    echo "  export PATH=\$JAVA_HOME/bin:\$PATH"
    exit 1
fi

JAVA_VERSION_OUTPUT=$(java -version 2>&1 | head -1)
JAVA_MAJOR=$(java -version 2>&1 | grep -oE '"[0-9]+' | head -1 | tr -d '"')
if [[ -z "$JAVA_MAJOR" ]]; then
    echo "WARNING: Could not parse Java version from: $JAVA_VERSION_OUTPUT"
    echo "Proceeding — if the terminal fails, install Java 21:"
    echo "  brew install openjdk@21"
elif [[ "$JAVA_MAJOR" -lt "$MIN_JAVA_VERSION" ]]; then
    echo "ERROR: Java $MIN_JAVA_VERSION required; found Java $JAVA_MAJOR."
    echo "Output: $JAVA_VERSION_OUTPUT"
    echo ""
    echo "Install Java 21:"
    echo "  brew install openjdk@21"
    echo "  export JAVA_HOME=/opt/homebrew/opt/openjdk@21"
    echo "  export PATH=\$JAVA_HOME/bin:\$PATH"
    exit 1
else
    echo "Java OK (major=$JAVA_MAJOR): $JAVA_VERSION_OUTPUT"
fi

# ── Jar presence check ────────────────────────────────────────────────────────
mkdir -p "$THETA_DIR"

if [[ ! -f "$JAR_PATH" ]]; then
    echo ""
    echo "ERROR: ThetaTerminalv3.jar not found at $JAR_PATH"
    echo ""
    echo "Download from your ThetaData account or the stable release:"
    echo "  mkdir -p $THETA_DIR"
    echo "  # Download ThetaTerminalv3.jar to $JAR_PATH"
    echo ""
    echo "Visit https://thetadata.us/account to download."
    echo "Then re-run this script."
    exit 1
fi

# ── Kill any existing terminal process ───────────────────────────────────────
# ThetaTerminalv3.jar is a BOOTSTRAPPER: it spawns the real server as an inner
# JVM from $THETA_DIR/lib/<build>.jar (orphaned to PPID 1, holds port 25503).
# Match BOTH jars — killing only the outer one leaves a stale inner server on
# the port and the relaunch dies silently (measured 2026-07-16).
EXISTING=$(pgrep -f "theta/ThetaTerminalv3\.jar|theta/lib/[^ ]*\.jar" 2>/dev/null || true)
if [[ -n "$EXISTING" ]]; then
    echo "Existing Theta Terminal v3 process(es) found — killing PID(s): $(echo "$EXISTING" | tr '\n' ' ')"
    # shellcheck disable=SC2086  # word-splitting on PIDs is intended
    kill $EXISTING 2>/dev/null || true
    sleep 2
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "Launching ThetaData Terminal v3..."
echo "  Jar:  $JAR_PATH"
echo "  Log:  $LOG_PATH"
echo "  JAVA_HOME: ${JAVA_HOME:-not set}"
echo "  (API key passed via environment, not argv — never echoed)"
echo ""

# Launch headless; nohup so it survives the shell exit.
# The key goes to the JVM as the THETADATA_API_KEY env var (shell prefix
# assignment — scoped to this one child process, never appears in argv).
THETADATA_API_KEY="$THETA_KEY" nohup java -jar "$JAR_PATH" \
    > "$LOG_PATH" 2>&1 &
THETA_PID=$!

echo "ThetaData Terminal v3 launched — PID $THETA_PID"
echo "Log: tail -f $LOG_PATH"
echo ""
echo "Health check (give it 5–10s to start):"
echo "  curl -s '$HEALTH_URL' | head -5"
echo ""
echo "Or probe via the backfill driver:"
echo "  python -m scripts.backfill_thetadata_eod --probe"
