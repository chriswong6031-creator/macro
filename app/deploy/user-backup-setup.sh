#!/usr/bin/env bash
# Install the MMX-001 customer-table backup timer.
# Operator-gated: this script does not run from update.sh and does not start a
# dump until /etc/macro-user-backup.env exists with BACKUP_ENCRYPTION_KEY.
#
# Usage (as root, on the VPS, after the repo pull):
#   APP_DIR=/opt/macro /opt/macro/app/deploy/user-backup-setup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/macro}"
STATE_DIR="${USER_BACKUP_DIR:-/var/lib/macro-user-backup}"
ENV_FILE="${USER_BACKUP_ENV:-/etc/macro-user-backup.env}"
SERVICE_SRC="$APP_DIR/app/deploy/macro-user-backup.service"
TIMER_SRC="$APP_DIR/app/deploy/macro-user-backup.timer"

if [[ ! -f "$SERVICE_SRC" || ! -f "$TIMER_SRC" ]]; then
	echo "user-backup-setup: missing unit sources under $APP_DIR/app/deploy" >&2
	exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
	echo "user-backup-setup: $ENV_FILE is absent." >&2
	echo "Create it as root, mode 0600, with at least:" >&2
	echo "  BACKUP_ENCRYPTION_KEY=<16+ chars, keep offline too>" >&2
	echo "  R2_ENDPOINT=..." >&2
	echo "  R2_ACCESS_KEY_ID=..." >&2
	echo "  R2_SECRET_ACCESS_KEY=..." >&2
	echo "  R2_BUCKET=..." >&2
	echo "  SUPABASE_URL=...          # or inherit from /etc/macro-api.env" >&2
	echo "  SUPABASE_SERVICE_ROLE_KEY=..." >&2
	echo "  BACKUP_R2_PREFIX=backups/user-tables" >&2
	exit 1
fi

if ! grep -qE '^BACKUP_ENCRYPTION_KEY=.+' "$ENV_FILE"; then
	echo "user-backup-setup: BACKUP_ENCRYPTION_KEY is missing from $ENV_FILE" >&2
	exit 1
fi

install -d -m 0700 "$STATE_DIR"

if ! systemd-analyze verify "$SERVICE_SRC" "$TIMER_SRC"; then
	echo "user-backup-setup: systemd-analyze verify failed — refusing install" >&2
	exit 1
fi

updated=0
for src in "$SERVICE_SRC" "$TIMER_SRC"; do
	unit=$(basename "$src")
	dest="/etc/systemd/system/$unit"
	if [[ ! -f "$dest" ]] || ! cmp -s "$src" "$dest"; then
		install -m 0644 "$src" "$dest"
		updated=1
	fi
done

if [[ "$updated" -eq 1 ]]; then
	systemctl daemon-reload
fi

systemctl enable --now macro-user-backup.timer
systemctl is-enabled macro-user-backup.timer >/dev/null
echo "user-backup-setup: macro-user-backup.timer enabled"
systemctl list-timers macro-user-backup.timer --no-pager
