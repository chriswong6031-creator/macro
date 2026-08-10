#!/usr/bin/env bash
# Slice 2 — deploy the FastAPI serving tier (macro-api) on the droplet.
# Builds a minimal venv (NOT the heavy engine stack), installs the serving and
# private Market Memory source/context/identity/breadth/technical units, and starts their
# public-safe or API-inaccessible lanes.
# Idempotent. Run AFTER setup.sh (which installs the Caddyfile that proxies /api/* here).
#   bash /opt/macro/app/deploy/api-setup.sh
set -euo pipefail

APP_DIR="/opt/macro"
VENV="/opt/macro-api/.venv"
log() { echo "[api-setup] $*"; }

log "[1/5] python venv + minimal deps"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y python3-venv >/dev/null 2>&1 || true
mkdir -p /opt/macro-api
test -d "$VENV" || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP_DIR/app/requirements.txt"
sha256sum "$APP_DIR/app/requirements.txt" | cut -d' ' -f1 > /opt/macro-api/.requirements.sha256

log "[2/5] pinned Codex runtime"
bash "$APP_DIR/app/deploy/codex-runtime-setup.sh"

log "[3/5] systemd units + private Market Memory state"
# The unit's Market Memory bind is deliberately non-optional and read-only.
# Provision it before installation so a fresh host fails closed without making
# the first service start impossible.
install -d -m 0700 /var/lib/macro-market-memory
install -d -m 0700 /var/lib/macro-market-memory/public
install -d -m 0700 /var/lib/macro-market-memory/public/trusted-v1
install -d -m 0700 /var/lib/macro-market-memory/state
install -d -m 0700 /var/lib/macro-market-memory/state/sources
install -d -m 0700 /var/lib/macro-market-memory/state/context-projection
install -d -m 0700 /var/lib/macro-market-memory/state/identity-v1
install -d -m 0700 /var/lib/macro-market-memory/state/breadth-v1
install -d -m 0700 /var/lib/macro-market-memory/state/technicals-v1
systemd-analyze verify \
  "$APP_DIR/app/deploy/macro-api.service" \
  "$APP_DIR/app/deploy/macro-market-memory-source.service" \
  "$APP_DIR/app/deploy/macro-market-memory-source.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-context.service" \
  "$APP_DIR/app/deploy/macro-market-memory-context.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-identity.service" \
  "$APP_DIR/app/deploy/macro-market-memory-identity.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-breadth.service" \
  "$APP_DIR/app/deploy/macro-market-memory-breadth.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-technicals.service" \
  "$APP_DIR/app/deploy/macro-market-memory-technicals.timer"
install -m 0644 "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-source.service" /etc/systemd/system/macro-market-memory-source.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-source.timer" /etc/systemd/system/macro-market-memory-source.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-context.service" /etc/systemd/system/macro-market-memory-context.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-context.timer" /etc/systemd/system/macro-market-memory-context.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-identity.service" /etc/systemd/system/macro-market-memory-identity.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-identity.timer" /etc/systemd/system/macro-market-memory-identity.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-breadth.service" /etc/systemd/system/macro-market-memory-breadth.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-breadth.timer" /etc/systemd/system/macro-market-memory-breadth.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-technicals.service" /etc/systemd/system/macro-market-memory-technicals.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-technicals.timer" /etc/systemd/system/macro-market-memory-technicals.timer
systemctl daemon-reload

log "[4/5] initialize trusted context + start serving and retry timers"
systemctl enable macro-api >/dev/null 2>&1 || true
# This oneshot initializes a complete empty trusted generation before strict
# projection. A source rejection is retryable and cannot make the API store
# incomplete or cause a nearest/current fallback.
systemctl start macro-market-memory-context.service || \
  log "trusted context projection failed closed; timer will retry"
systemctl start macro-market-memory-identity.service || \
  log "private identity observation accrual failed closed; timer will retry"
systemctl start macro-market-memory-breadth.service || \
  log "private breadth actual-output capture failed closed; timer will retry"
systemctl start macro-market-memory-technicals.service || \
  log "private technical actual-output capture failed closed; timer will retry"
systemctl restart macro-api
systemctl enable --now macro-market-memory-source.timer
systemctl enable --now macro-market-memory-context.timer
systemctl enable --now macro-market-memory-identity.timer
systemctl enable --now macro-market-memory-breadth.timer
systemctl enable --now macro-market-memory-technicals.timer

log "[5/5] health check (local)"
sleep 2
curl -fsS http://127.0.0.1:8000/api/health && echo
log "DONE — macro-api on 127.0.0.1:8000 (Caddy proxies /api/* here)"
