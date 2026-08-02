#!/usr/bin/env bash
# Provision the isolated B1 BioCatalyst collector lane.
#
# This script intentionally installs no credentials and never enables or starts
# the timer.  Its only durable runtime inputs live in the root-owned env file.
set -euo pipefail

APP_DIR=/opt/macro
SERVICE_SOURCE="$APP_DIR/app/deploy/macro-biocatalyst.service"
TIMER_SOURCE="$APP_DIR/app/deploy/macro-biocatalyst.timer"
SERVICE_DEST=/etc/systemd/system/macro-biocatalyst.service
TIMER_DEST=/etc/systemd/system/macro-biocatalyst.timer
ENV_FILE=/etc/macro-biocatalyst.env
STATE_ROOT=/var/lib/macro-biocatalyst
SERVICE_USER=macro-biocatalyst
SERVICE_GROUP=macro-biocatalyst
RUNTIME_ROOT=/opt/macro-biocatalyst
BIOCATALYST_CURRENT="$RUNTIME_ROOT/current"
REQUIREMENTS_SOURCE="$APP_DIR/app/deploy/biocatalyst-requirements.txt"
RUNTIME_INSTALLER="$APP_DIR/app/deploy/biocatalyst-runtime.sh"
SECURE_PATH_HELPER="$APP_DIR/app/deploy/biocatalyst-secure-paths.py"

log() {
	echo "biocatalyst-setup: $*"
}

die() {
	log "$*" >&2
	exit 1
}

usage() {
	cat <<'USAGE'
Usage: biocatalyst-setup.sh [--verify-prereqs]

Installs the BioCatalyst systemd service and timer without enabling either one.
The root-owned /etc/macro-biocatalyst.env file must contain:
  BIOCATALYST_ENABLED=1
  BIOCATALYST_CANARY_NCTS=<comma-separated NCT ids>
  BIOCATALYST_USER_AGENT=<descriptive contact string>
  BIOCATALYST_R2_ENDPOINT=<BioCatalyst-scoped endpoint>
  BIOCATALYST_R2_BUCKET=<BioCatalyst-scoped bucket>
  BIOCATALYST_R2_ACCESS_KEY_ID=<scoped access key>
  BIOCATALYST_R2_SECRET_ACCESS_KEY=<scoped secret>

--verify-prereqs checks only that the required keys are non-empty; it never
prints their values, verifies the isolated dependency runtime, and does not arm
the timer. The runtime is an immutable versioned virtualenv published through
the stable /opt/macro-biocatalyst/current symlink. Use the operations runbook
for the explicit operator arming step after this check passes.
USAGE
}

required_env_keys=(
	BIOCATALYST_ENABLED
	BIOCATALYST_CANARY_NCTS
	BIOCATALYST_USER_AGENT
	BIOCATALYST_R2_ENDPOINT
	BIOCATALYST_R2_BUCKET
	BIOCATALYST_R2_ACCESS_KEY_ID
	BIOCATALYST_R2_SECRET_ACCESS_KEY
)

verify_prereqs() {
	local key
	local missing=()

	for key in "${required_env_keys[@]}"; do
		if ! grep -Eq "^${key}=.+" "$ENV_FILE"; then
			missing+=("$key")
		fi
	done

	if ! grep -Eq '^BIOCATALYST_ENABLED=1([[:space:]]*)$' "$ENV_FILE"; then
		missing+=("BIOCATALYST_ENABLED must equal 1")
	fi

	if [ "${#missing[@]}" -gt 0 ]; then
		log "prerequisites incomplete in $ENV_FILE: ${missing[*]}" >&2
		return 1
	fi

	log "root-owned BioCatalyst prerequisites verified"
}

verify_units() {
	if command -v systemd-analyze >/dev/null 2>&1; then
		systemd-analyze verify "$SERVICE_SOURCE" "$TIMER_SOURCE"
	else
		log "systemd-analyze unavailable; skipped unit verification"
	fi
}

ensure_service_identity() {
	local passwd_entry account_name account_uid account_gid account_gecos account_home account_shell
	if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
		groupadd --system "$SERVICE_GROUP"
	fi
	if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
		useradd --system --gid "$SERVICE_GROUP" --home-dir "$STATE_ROOT" \
			--no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
	fi
	[ "$(id -g "$SERVICE_USER")" = "$(getent group "$SERVICE_GROUP" | awk -F: '{print $3}')" ] || \
		die "$SERVICE_USER must use $SERVICE_GROUP as its primary group"
	passwd_entry="$(getent passwd "$SERVICE_USER")" || die "cannot inspect $SERVICE_USER"
	IFS=: read -r account_name _ account_uid account_gid account_gecos account_home account_shell <<<"$passwd_entry"
	[ "$account_name" = "$SERVICE_USER" ] || die "unexpected BioCatalyst service identity"
	[ "$account_home" = "$STATE_ROOT" ] || die "$SERVICE_USER has an unexpected home directory"
	case "$account_shell" in
		*/nologin|*/false) ;;
		*) die "$SERVICE_USER must use a non-login shell" ;;
	esac
}

verify_runtime() {
	[ -L "$BIOCATALYST_CURRENT" ] || die "isolated runtime pointer missing: $BIOCATALYST_CURRENT"
	bash "$RUNTIME_INSTALLER" --verify
}

install_runtime() {
	bash "$RUNTIME_INSTALLER" --install "$REQUIREMENTS_SOURCE"
}

main() {
	local verify_only=0

	case "${1:-}" in
		"") ;;
		--verify-prereqs) verify_only=1 ;;
		--help|-h) usage; exit 0 ;;
		*) usage >&2; die "unknown argument: $1" ;;
	esac

	[ "$(id -u)" -eq 0 ] || die "must run as root"
	[ -f "$SERVICE_SOURCE" ] || die "missing service source: $SERVICE_SOURCE"
	[ -f "$TIMER_SOURCE" ] || die "missing timer source: $TIMER_SOURCE"
	[ -f "$REQUIREMENTS_SOURCE" ] || die "missing requirements source: $REQUIREMENTS_SOURCE"
	[ -f "$RUNTIME_INSTALLER" ] || die "missing runtime installer: $RUNTIME_INSTALLER"
	[ -f "$SECURE_PATH_HELPER" ] || die "missing secure path helper: $SECURE_PATH_HELPER"
	command -v python3 >/dev/null 2>&1 || die "python3 is required for secure provisioning"

	ensure_service_identity
	SERVICE_UID="$(id -u "$SERVICE_USER")"
	SERVICE_GID="$(id -g "$SERVICE_USER")"
	ROOT_UID="$(id -u root)"
	ROOT_GID="$(id -g root)"
	python3 "$SECURE_PATH_HELPER" provision-state \
		--state-root "$STATE_ROOT" \
		--env-file "$ENV_FILE" \
		--service-uid "$SERVICE_UID" \
		--service-gid "$SERVICE_GID" \
		--root-uid "$ROOT_UID" \
		--env-uid "$ROOT_UID" \
		--env-gid "$ROOT_GID"

	if [ "$verify_only" -eq 1 ]; then
		verify_prereqs
		verify_runtime
		verify_units
		log "timer remains disabled; follow the operations runbook to arm it"
		exit 0
	fi

	install_runtime
	verify_units
	command -v systemctl >/dev/null 2>&1 || die "systemctl is required to install units"
	install -m 0644 "$SERVICE_SOURCE" "$SERVICE_DEST"
	install -m 0644 "$TIMER_SOURCE" "$TIMER_DEST"
	systemctl daemon-reload
	log "units installed, but intentionally left disabled"
	log "populate $ENV_FILE, run --verify-prereqs, then follow the operations runbook"
}

main "$@"
