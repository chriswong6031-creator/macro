#!/usr/bin/env bash
# Refresh the served site to the latest main, then reload Caddy.
# Installed as /usr/local/bin/macro-update by setup.sh; run by cron (nightly) or by hand.
set -euo pipefail
APP_DIR="/opt/macro"
git -C "$APP_DIR" fetch --depth 1 origin main
git -C "$APP_DIR" reset --hard FETCH_HEAD
systemctl reload caddy 2>/dev/null || systemctl restart caddy
echo "macro-update $(date -u +%FT%TZ) -> $(git -C "$APP_DIR" rev-parse --short HEAD)"
