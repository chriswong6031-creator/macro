#!/usr/bin/env bash
# scripts/launchd/theta_terminal_keepalive.sh
#
# launchd guard wrapper that keeps the ThetaData Terminal v3 alive on :25503.
# Installed 2026-07-20 after the 07-17..07-20 outage: the terminal only ever ran
# nohup'd from an interactive shell — when that tty closed, stdin EOF shut the
# terminal down cleanly ("WARN: Shutting down terminal") and NOTHING restarted
# it, so every EOD options lane (backfill → hub → levels/vex/moves → pre-open
# ledger seal) starved silently.
#
# CONTRACT:
#   (a) If http://127.0.0.1:25503 already answers → exit 0 (healthy).
#       launchd (KeepAlive) re-invokes after ThrottleInterval — this is the
#       cheap health poll loop.
#   (b) If a ThetaTerminalv3.jar process already exists → exit 0 (starting up,
#       or owned by a manual shell — never spawn a duplicate).
#   (c) Launch the terminal in the FOREGROUND with stdin held open by an
#       infinite pipe (tail -f /dev/null |). stdin EOF is the v3 shutdown
#       trigger — never launch it with stdin on /dev/null or a mortal tty.
#       Wrapper lifetime == terminal lifetime, so launchd sees exits.
#   (d) If the terminal dies within FAST_DEATH_S seconds (auth failure / bad
#       config insta-death), sleep BACKOFF_S before exiting so a stale
#       THETA_API_KEY does not hammer the ThetaData auth endpoint 1440x/day.
#       (2026-07-20: the THETA_API_KEY in .env returns 401 — operator must
#       refresh it at https://thetadata.us/account; this wrapper auto-heals
#       within ~5 min of the key being fixed in .env.)
#   (e) Terminal output appends to ~/theta/terminal_v3.log (stamped per launch).
#       NEVER echo THETA_API_KEY.
#
# Install (once):
#   cp scripts/launchd/com.macro.theta-terminal.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.macro.theta-terminal.plist
#
# Uninstall:
#   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.macro.theta-terminal.plist

set -uo pipefail

THETA_OPS_WT="/Users/chriswong/theta-ops-wt"
JAR_PATH="/Users/chriswong/theta/ThetaTerminalv3.jar"
TERM_LOG="/Users/chriswong/theta/terminal_v3.log"
HEALTH_URL="http://127.0.0.1:25503/v3/option/list/symbols"
FAST_DEATH_S=30
BACKOFF_S=240

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# --- (a) Already healthy? -----------------------------------------------------
code=$(curl -s -m 6 -o /dev/null -w '%{http_code}' "${HEALTH_URL}" 2>/dev/null); code="${code:-000}"
if [ "${code}" = "200" ]; then
    exit 0
fi

# --- (b) Process already exists (starting up / manual)? -----------------------
if pgrep -f "ThetaTerminalv3.jar" > /dev/null 2>&1; then
    echo "[$(stamp)] theta_terminal_keepalive: process exists but health=${code} — leaving it alone"
    exit 0
fi

# --- Env: java 21 + THETA_API_KEY from .env (never echoed) --------------------
export JAVA_HOME="/opt/homebrew/opt/openjdk@21"
export PATH="${JAVA_HOME}/bin:${PATH}"

# Plain dot-source (the run_with_env.sh house pattern) — process substitution
# (source <(grep ...)) silently loads nothing under launchd's /bin/bash 3.2.
if [ -f "${THETA_OPS_WT}/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    . "${THETA_OPS_WT}/.env"
    set +o allexport
fi

if [ -z "${THETA_API_KEY:-}" ]; then
    echo "[$(stamp)] theta_terminal_keepalive: THETA_API_KEY missing from ${THETA_OPS_WT}/.env — backing off ${BACKOFF_S}s"
    sleep "${BACKOFF_S}"
    exit 1
fi

if [ ! -f "${JAR_PATH}" ]; then
    echo "[$(stamp)] theta_terminal_keepalive: jar missing at ${JAR_PATH} — backing off ${BACKOFF_S}s"
    sleep "${BACKOFF_S}"
    exit 1
fi

# --- (c) Foreground launch, stdin held open -----------------------------------
echo "[$(stamp)] theta_terminal_keepalive: launching terminal (health was ${code})"
echo "[$(stamp)] ---- keepalive launch ----" >> "${TERM_LOG}"
t0=$(date +%s)
tail -f /dev/null | java -jar "${JAR_PATH}" --api-key "${THETA_API_KEY}" >> "${TERM_LOG}" 2>&1
rc=$?
t1=$(date +%s)
elapsed=$(( t1 - t0 ))
echo "[$(stamp)] theta_terminal_keepalive: terminal exited rc=${rc} after ${elapsed}s"

# --- (d) Insta-death backoff (auth failure shape) -----------------------------
if [ "${elapsed}" -lt "${FAST_DEATH_S}" ]; then
    echo "[$(stamp)] theta_terminal_keepalive: died in <${FAST_DEATH_S}s (likely auth/config) — backing off ${BACKOFF_S}s"
    sleep "${BACKOFF_S}"
fi

exit 1
