#!/usr/bin/env bash
# Slice 2 — deploy the FastAPI serving tier (macro-api) on the droplet.
# Builds a minimal venv (NOT the heavy engine stack), installs a systemd unit, starts it.
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

log "[3/5] systemd unit"
install -m 0644 "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service
systemctl daemon-reload

log "[4/5] start service"
systemctl enable macro-api >/dev/null 2>&1 || true
systemctl restart macro-api

log "[5/5] health check (local)"
sleep 2
curl -fsS http://127.0.0.1:8000/api/health && echo
log "DONE — macro-api on 127.0.0.1:8000 (Caddy proxies /api/* here)"
