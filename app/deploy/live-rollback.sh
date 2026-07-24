#!/usr/bin/env bash
# Stop the VPS live plane and recover the pre-cutover live path.
#
# This is intentionally non-destructive: externally published artifacts are
# moved to a timestamped backup so Caddy immediately falls back to the last
# site.served copies, and private state/data remain available for diagnosis.
set -euo pipefail

BASE_DIR="/var/lib/macro-live"
PUBLIC_DIR="$BASE_DIR/public"
LEGACY_CRON='*/5 1-21 * * 1-5 /usr/local/bin/macro-live >> /var/log/macro-live.log 2>&1'
log() { echo "[live-rollback] $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "live-rollback must run as root" >&2
  exit 1
fi

log "[1/3] stop replacement timers"
systemctl disable --now \
  macro-live-fast.timer \
  macro-live-snapshot.timer \
  macro-live-bars.timer >/dev/null 2>&1 || true
systemctl stop \
  macro-live-fast.service \
  macro-live-snapshot.service \
  macro-live-bars.service >/dev/null 2>&1 || true

log "[2/3] restore legacy cron writer if needed"
tmp_cron=$(mktemp)
cleanup() { rm -f "$tmp_cron"; }
trap cleanup EXIT
crontab -l 2>/dev/null > "$tmp_cron" || true
if ! grep -qF '/usr/local/bin/macro-live' "$tmp_cron"; then
  echo "$LEGACY_CRON" >> "$tmp_cron"
  crontab "$tmp_cron"
fi
cleanup
trap - EXIT

log "[3/3] withdraw external browser artifacts"
if [ -d "$PUBLIC_DIR" ]; then
  backup_dir="$BASE_DIR/public.rollback.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$PUBLIC_DIR" "$backup_dir"
  log "external artifacts preserved at $backup_dir"
fi

log "DONE — legacy cron is primary; private state/data were retained"
