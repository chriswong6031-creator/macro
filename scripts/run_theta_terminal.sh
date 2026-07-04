#!/usr/bin/env bash
# scripts/run_theta_terminal.sh — launch the ThetaData Terminal Java client.
#
# The Theta Terminal is a local Java process that serves the ThetaData REST API on
# http://127.0.0.1:25510.  It must be running before any collectors/thetadata.py call.
#
# Credentials (never echoed):
#   - Primary: THETA_USERNAME / THETA_PASSWORD environment variables
#   - Fallback: .env file at the repo root (KEY=VALUE format, one per line)
#
# Jar location: ~/theta/ThetaTerminal.jar
#   If absent, instructions are printed.  The stable jar is downloaded from:
#   https://download-stable.thetadata.us/ThetaTerminal.jar
#
# Java requirement: Java 17+.  The script checks and exits with a clear error if
# the installed java is older or absent.
#
# Usage:
#   scripts/run_theta_terminal.sh
#   THETA_USERNAME=user@example.com THETA_PASSWORD=secret scripts/run_theta_terminal.sh

set -euo pipefail

THETA_DIR="$HOME/theta"
JAR_PATH="$THETA_DIR/ThetaTerminal.jar"
LOG_PATH="$THETA_DIR/terminal.log"
STABLE_JAR_URL="https://download-stable.thetadata.us/ThetaTerminal.jar"
MIN_JAVA_VERSION=17

# ── Credential resolution (never echo the password) ───────────────────────────
_load_env() {
    # Load .env from repo root if it exists
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

THETA_USER="${THETA_USERNAME:-}"
# THETA_PASSWORD is read but never printed — only passed directly to the JVM call
THETA_PASS="${THETA_PASSWORD:-}"

if [[ -z "$THETA_USER" || -z "$THETA_PASS" ]]; then
    echo "ERROR: THETA_USERNAME and/or THETA_PASSWORD not set."
    echo ""
    echo "Set them in your environment:"
    echo "  export THETA_USERNAME=your@email.com"
    echo "  export THETA_PASSWORD=yourpassword"
    echo ""
    echo "Or add them to .env at the repo root:"
    echo "  THETA_USERNAME=your@email.com"
    echo "  THETA_PASSWORD=yourpassword"
    exit 1
fi

# ── Java version check ────────────────────────────────────────────────────────
if ! command -v java &>/dev/null; then
    echo "ERROR: 'java' not found in PATH."
    echo "Install Java 17+ from https://adoptium.net/ or via Homebrew:"
    echo "  brew install --cask temurin@21"
    exit 1
fi

JAVA_VERSION_OUTPUT=$(java -version 2>&1 | head -1)
# java -version prints: java version "17.0.x" or openjdk version "21.0.x"
JAVA_MAJOR=$(java -version 2>&1 | grep -oE '"[0-9]+' | head -1 | tr -d '"')
if [[ -z "$JAVA_MAJOR" ]]; then
    echo "WARNING: Could not parse Java version from: $JAVA_VERSION_OUTPUT"
    echo "Proceeding anyway — if the terminal fails, install Java 17+."
elif [[ "$JAVA_MAJOR" -lt "$MIN_JAVA_VERSION" ]]; then
    echo "ERROR: Java $MIN_JAVA_VERSION+ required; found Java $JAVA_MAJOR."
    echo "Output: $JAVA_VERSION_OUTPUT"
    echo "Install Java 17+ from https://adoptium.net/ or:"
    echo "  brew install --cask temurin@21"
    exit 1
else
    echo "Java OK: $(java -version 2>&1 | head -1)"
fi

# ── Jar presence check ────────────────────────────────────────────────────────
mkdir -p "$THETA_DIR"

if [[ ! -f "$JAR_PATH" ]]; then
    echo ""
    echo "ERROR: ThetaTerminal.jar not found at $JAR_PATH"
    echo ""
    echo "Download the stable jar:"
    echo "  mkdir -p $THETA_DIR"
    echo "  curl -L -o $JAR_PATH $STABLE_JAR_URL"
    echo ""
    echo "Or visit https://download-stable.thetadata.us/ to download manually."
    echo "Then re-run this script."
    exit 1
fi

# ── Kill any existing terminal process ───────────────────────────────────────
EXISTING=$(pgrep -f "ThetaTerminal.jar" 2>/dev/null || true)
if [[ -n "$EXISTING" ]]; then
    echo "Existing Theta Terminal process found (PID $EXISTING) — killing..."
    kill "$EXISTING" 2>/dev/null || true
    sleep 1
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "Launching Theta Terminal..."
echo "  Jar:  $JAR_PATH"
echo "  Log:  $LOG_PATH"
echo "  User: $THETA_USER"
echo "  (Password not echoed)"
echo ""

# Launch headless; nohup so it survives the shell exit
# NEVER echo the password — it is passed directly to the process
nohup java -jar "$JAR_PATH" "$THETA_USER" "$THETA_PASS" \
    > "$LOG_PATH" 2>&1 &
THETA_PID=$!

echo "Theta Terminal launched — PID $THETA_PID"
echo "Log: tail -f $LOG_PATH"
echo ""
echo "Health check (give it 5–10s to start):"
echo "  curl -s http://127.0.0.1:25510/v2/list/roots/option | head -c 200"
echo ""
echo "Or probe via the backfill driver:"
echo "  python -m scripts.backfill_thetadata_eod --probe"
