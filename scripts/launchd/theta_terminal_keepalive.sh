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
#   (a) If http://127.0.0.1:25503 answers 200 on /v3/option/list/symbols with a
#       NON-TRIVIAL body (> SYMBOLS_MIN_BYTES) → exit 0 (healthy). launchd
#       (KeepAlive) re-invokes after ThrottleInterval — this is the cheap
#       health poll loop. A bare 200 is NOT health: a terminal running on a
#       stale/revoked THETA_API_KEY stays up as a ZOMBIE — HTTP 200 with an
#       EMPTY body on the symbols endpoint while real data endpoints time out
#       (bit live 2026-07-20 ~12:04Z; recovery needed a manual kill because
#       this check and the sentinel both trusted the status code).
#   (a2) Zombie shape (200 + trivial body) on TWO consecutive polls (strike
#       file, < ZOMBIE_STRIKE_WINDOW_S apart) → kill the terminal (the
#       bootstrapper jar by pattern + whatever LISTENs on :25503 — the inner
#       lib jar holds the port and can orphan-survive the bootstrapper) and
#       exit; the next launchd fire relaunches via (c) with a fresh .env read,
#       after the port has had time to release.
#   (b) If a ThetaTerminalv3.jar process exists and the port doesn't answer →
#       exit 0 (starting up, or owned by a manual shell — never spawn a
#       duplicate).
#   (c) Launch the terminal with stdin held open on an anonymous FIFO (fd 9),
#       java BACKGROUNDED with this wrapper as its zombie watchdog: launchd
#       cannot re-invoke this job while the wrapper is alive, so a
#       keepalive-owned zombie is invisible to (a)/(a2) — the wrapper must
#       police its own child. The watchdog probes every WATCH_INTERVAL_S; two
#       consecutive zombie reads → recycle. Wrapper lifetime == terminal
#       lifetime still holds (the loop exits within ~5 s of java dying), so
#       launchd sees exits. stdin EOF is the v3 shutdown trigger — never
#       launch with stdin on /dev/null or a mortal tty.
#   (d) If the terminal dies within FAST_DEATH_S seconds (auth failure / bad
#       config insta-death) OR was recycled as a zombie (the stale-key shape),
#       sleep BACKOFF_S before exiting so a stale THETA_API_KEY does not
#       hammer the ThetaData auth endpoint 1440x/day.
#   (e) Terminal output appends to ~/theta/terminal_v3.log (stamped per launch).
#       NEVER echo THETA_API_KEY. It reaches the JVM as the THETADATA_API_KEY
#       env var, never as --api-key argv (argv is world-readable via ps).
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
SYMBOLS_MIN_BYTES=1000        # healthy full list ≈ 106 KB / 15.6k roots; zombie = 0 B
ZOMBIE_STRIKE_FILE="/tmp/theta_terminal_zombie.strike"
ZOMBIE_STRIKE_WINDOW_S=300
WATCH_INTERVAL_S=60
FAST_DEATH_S=30
BACKOFF_S=240

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

probe_health() {
    # Sets: code (http status, 000 on no-answer) + body_bytes. The body is
    # counted, never echoed, and never persisted past the probe.
    local tmp
    tmp="$(mktemp /tmp/theta_keepalive_health.XXXXXX)" || { code="000"; body_bytes=0; return; }
    code=$(curl -s -m 6 -o "${tmp}" -w '%{http_code}' "${HEALTH_URL}" 2>/dev/null); code="${code:-000}"
    body_bytes=$(wc -c < "${tmp}" 2>/dev/null | tr -d '[:space:]'); body_bytes="${body_bytes:-0}"
    rm -f "${tmp}"
}

kill_port_holders() {
    # Kill whatever LISTENs on :25503. LISTEN-only on purpose: clients with a
    # socket open to the port (e.g. a backfill mid-request) must never be hit.
    local pids
    pids=$(lsof -nP -tiTCP:25503 -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "${pids}" ]; then
        echo "[$(stamp)] theta_terminal_keepalive: killing :25503 listeners: ${pids}"
        # shellcheck disable=SC2086
        kill ${pids} 2>/dev/null
        sleep 3
        pids=$(lsof -nP -tiTCP:25503 -sTCP:LISTEN 2>/dev/null || true)
        # shellcheck disable=SC2086
        [ -n "${pids}" ] && kill -9 ${pids} 2>/dev/null
    fi
    return 0
}

# --- (a) Already healthy? -----------------------------------------------------
probe_health
if [ "${code}" = "200" ] && [ "${body_bytes}" -gt "${SYMBOLS_MIN_BYTES}" ]; then
    rm -f "${ZOMBIE_STRIKE_FILE}"
    exit 0
fi

# --- (a2) Zombie recycle (externally-owned terminal) --------------------------
# 200 + trivial body = fully up but serving nothing. A booting terminal REFUSES
# the socket (code 000) — it never answers empty 200s — so this shape is never
# "starting up". Two consecutive strikes before killing, so a one-off transient
# can't take down a live terminal. (A keepalive-owned zombie never reaches this
# code — launchd doesn't re-invoke while the wrapper runs; that case is the
# in-run watchdog in (c).)
if [ "${code}" = "200" ]; then
    now_s=$(date +%s)
    strike_age=999999
    if [ -f "${ZOMBIE_STRIKE_FILE}" ]; then
        strike_s=$(cat "${ZOMBIE_STRIKE_FILE}" 2>/dev/null | tr -cd '0-9')
        strike_age=$(( now_s - ${strike_s:-0} ))
    fi
    if [ "${strike_age}" -le "${ZOMBIE_STRIKE_WINDOW_S}" ]; then
        echo "[$(stamp)] theta_terminal_keepalive: ZOMBIE confirmed (http=200, body=${body_bytes}B, strikes ${strike_age}s apart) — recycling terminal"
        rm -f "${ZOMBIE_STRIKE_FILE}"
        pkill -f "ThetaTerminalv3.jar" 2>/dev/null
        sleep 3
        kill_port_holders
        exit 1
    fi
    echo "[$(stamp)] theta_terminal_keepalive: zombie shape (http=200, body=${body_bytes}B <= ${SYMBOLS_MIN_BYTES}B) — strike 1, recheck next poll"
    echo "${now_s}" > "${ZOMBIE_STRIKE_FILE}"
    exit 0
fi
rm -f "${ZOMBIE_STRIKE_FILE}"

# --- (b) Process already exists (starting up / manual)? -----------------------
if pgrep -f "ThetaTerminalv3.jar" > /dev/null 2>&1; then
    echo "[$(stamp)] theta_terminal_keepalive: process exists but health=${code}/${body_bytes}B — leaving it alone"
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

# --- (c) Launch: FIFO stdin + backgrounded java + zombie watchdog -------------
# stdin holder: an anonymous FIFO this wrapper holds open read-write on fd 9.
# The terminal's console reader blocks forever (never EOF). Do NOT use a
# `tail -f /dev/null | java` pipeline here: when java dies, the never-exiting
# tail keeps the pipeline (and so the wrapper) alive forever, launchd sees a
# running job, and no restart ever happens (learned 2026-07-20, first live死).
#
# java is BACKGROUNDED (same process group; the wrapper waits on it) so the
# wrapper can keep probing health while the terminal lives — a foreground java
# blocks the wrapper, launchd never re-invokes a running job, and a zombie
# would sit unpolled until a human notices (exactly the 2026-07-20 incident).
echo "[$(stamp)] theta_terminal_keepalive: launching terminal (health was ${code}/${body_bytes}B)"
echo "[$(stamp)] ---- keepalive launch ----" >> "${TERM_LOG}"
FIFO="/tmp/theta_terminal_stdin.$$"
rm -f "${FIFO}"
mkfifo "${FIFO}" || { echo "[$(stamp)] theta_terminal_keepalive: mkfifo failed"; sleep "${BACKOFF_S}"; exit 1; }
exec 9<>"${FIFO}"
rm -f "${FIFO}"
t0=$(date +%s)
# Key via THETADATA_API_KEY env (shell prefix, java-process-scoped) — NEVER the
# --api-key flag: argv is world-readable via ps (same fix as run_theta_terminal.sh).
THETADATA_API_KEY="${THETA_API_KEY}" java -jar "${JAR_PATH}" <&9 >> "${TERM_LOG}" 2>&1 &
JAVA_PID=$!

# Zombie watchdog: probe every WATCH_INTERVAL_S while java lives (java liveness
# rechecked every 5 s so a natural death still surfaces fast). A booting
# terminal refuses the socket (000) — never a strike; one-off transients reset
# the count. Two consecutive zombie reads → kill java + the :25503 listeners
# (the inner lib jar can orphan-survive the bootstrapper and hold the port,
# which would make the relaunch die "Address already in use").
zombie_recycled=0
strikes=0
tick=0
while kill -0 "${JAVA_PID}" 2>/dev/null; do
    sleep 5
    tick=$(( tick + 5 ))
    [ "${tick}" -lt "${WATCH_INTERVAL_S}" ] && continue
    tick=0
    kill -0 "${JAVA_PID}" 2>/dev/null || break
    probe_health
    if [ "${code}" = "200" ] && [ "${body_bytes}" -le "${SYMBOLS_MIN_BYTES}" ]; then
        strikes=$(( strikes + 1 ))
        echo "[$(stamp)] theta_terminal_keepalive: watchdog zombie strike ${strikes}/2 (http=200, body=${body_bytes}B)"
        if [ "${strikes}" -ge 2 ]; then
            echo "[$(stamp)] theta_terminal_keepalive: watchdog ZOMBIE confirmed — recycling terminal (pid ${JAVA_PID} + :25503 listeners)"
            zombie_recycled=1
            kill "${JAVA_PID}" 2>/dev/null
            sleep 3
            kill -0 "${JAVA_PID}" 2>/dev/null && kill -9 "${JAVA_PID}" 2>/dev/null
            kill_port_holders
            break
        fi
    else
        strikes=0
    fi
done
wait "${JAVA_PID}" 2>/dev/null
rc=$?
exec 9>&-
t1=$(date +%s)
elapsed=$(( t1 - t0 ))
echo "[$(stamp)] theta_terminal_keepalive: terminal exited rc=${rc} after ${elapsed}s"

# --- (d) Backoff (auth-failure shapes) ----------------------------------------
if [ "${zombie_recycled}" = "1" ]; then
    echo "[$(stamp)] theta_terminal_keepalive: zombie recycle (stale-key shape) — backing off ${BACKOFF_S}s before relaunch"
    sleep "${BACKOFF_S}"
elif [ "${elapsed}" -lt "${FAST_DEATH_S}" ]; then
    echo "[$(stamp)] theta_terminal_keepalive: died in <${FAST_DEATH_S}s (likely auth/config) — backing off ${BACKOFF_S}s"
    sleep "${BACKOFF_S}"
fi

exit 1
