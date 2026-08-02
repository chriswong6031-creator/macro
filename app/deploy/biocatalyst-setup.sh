#!/usr/bin/env bash
# Provision the isolated B1 BioCatalyst collector lane.
#
# This script intentionally installs no credentials and never enables or starts
# the timer.  Its only durable runtime inputs live in the root-owned env file.
set -euo pipefail

APP_DIR=/opt/macro
SERVICE_SOURCE="$APP_DIR/app/deploy/macro-biocatalyst.service"
TIMER_SOURCE="$APP_DIR/app/deploy/macro-biocatalyst.timer"
HEARTBEAT_SERVICE_SOURCE="$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service"
HEARTBEAT_TIMER_SOURCE="$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer"
HEARTBEAT_RUNNER="$APP_DIR/app/deploy/biocatalyst-activation-heartbeat.sh"
SERVICE_DEST=/etc/systemd/system/macro-biocatalyst.service
TIMER_DEST=/etc/systemd/system/macro-biocatalyst.timer
HEARTBEAT_SERVICE_DEST=/etc/systemd/system/macro-biocatalyst-activation-heartbeat.service
HEARTBEAT_TIMER_DEST=/etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer
ENV_FILE=/etc/macro-biocatalyst.env
CONTROL_ENV_FILE=/etc/macro-biocatalyst-control.env
STATE_ROOT=/var/lib/macro-biocatalyst
ACTIVATION_ROOT="$STATE_ROOT/activation"
ACTIVATION_GATE="$ACTIVATION_ROOT/gate.json"
ACTIVATION_HEARTBEAT="$ACTIVATION_ROOT/heartbeat.json"
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
  BIOCATALYST_HISTORY_ENABLED=0  # optional B2 adapter; keep 0 until separately reviewed
  BIOCATALYST_PROSPECTIVE_ENABLED=0  # B4E; default dark until the activation gate below
  BIOCATALYST_R2_ACTIVATION_ID=<r2_activation_24-hex-id>  # required only when prospective=1
  BIOCATALYST_R2_ACCOUNT_ID=<Cloudflare account id>  # required only when prospective=1
  BIOCATALYST_R2_JURISDICTION=default  # required only when prospective=1
  BIOCATALYST_R2_RETENTION_CONFIRMED=0  # deprecated evidence only; never authorizes collection
  BIOCATALYST_CANARY_NCTS=<comma-separated NCT ids>
  BIOCATALYST_USER_AGENT=<descriptive contact string>
  BIOCATALYST_R2_ENDPOINT=<BioCatalyst-scoped endpoint>
  BIOCATALYST_R2_BUCKET=<BioCatalyst-scoped bucket>
  BIOCATALYST_R2_ACCESS_KEY_ID=<scoped access key>
  BIOCATALYST_R2_SECRET_ACCESS_KEY=<scoped secret>

The separate root-only /etc/macro-biocatalyst-control.env file (mode 0600)
must contain, when prospective collection is enabled:
  BIOCATALYST_R2_CONTROL_ACCOUNT_ID=<Cloudflare account id>
  BIOCATALYST_R2_CONTROL_API_TOKEN=<Cloudflare control/auditor token>
  BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS=86400
  BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS=7200

The control token is never loaded by the collector. Root must seal the
root-controlled gate at /var/lib/macro-biocatalyst/activation/gate.json
before prospective collection can run. The root heartbeat timer is installed
but remains disabled until that seal is operationally armed. Renew the gate
before its 24-hour expiry; hourly heartbeats expire after two hours.

--verify-prereqs checks the required key shapes, trusted local paths, and the
fresh cryptographic gate/heartbeat contract without a remote request; it never
prints their values or arms the timer. The runtime is an immutable versioned virtualenv published through
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

required_control_env_keys=(
	BIOCATALYST_R2_CONTROL_ACCOUNT_ID
	BIOCATALYST_R2_CONTROL_API_TOKEN
	BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS
	BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS
)

require_nonempty_keys() {
	local file="$1"
	shift
	local key
	for key in "$@"; do
		if ! grep -Eq "^${key}=.+" "$file"; then
			missing+=("$key")
		fi
	done
}

gate_activation_id() {
	python3 - "$ACTIVATION_GATE" <<'PY'
import json
import re
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, UnicodeError, json.JSONDecodeError):
    raise SystemExit(1)
activation_id = payload.get("activation_id") if isinstance(payload, dict) else None
if not isinstance(activation_id, str) or not re.fullmatch(r"r2_activation_[a-f0-9]{24}", activation_id):
    raise SystemExit(1)
print(activation_id)
PY
}

validate_activation_artifacts() {
	"$BIOCATALYST_CURRENT/bin/python" - \
		"$BIOCATALYST_CURRENT/bin/python" \
		"$ENV_FILE" \
		"$CONTROL_ENV_FILE" \
		"$ACTIVATION_GATE" \
		"$ACTIVATION_HEARTBEAT" <<'PY'
from pathlib import Path
import re
import subprocess
import sys

python, worker_env_file, control_env_file, gate_file, heartbeat_file = sys.argv[1:]
_ENTRY = re.compile(r"([A-Z][A-Z0-9_]*)=([^\r\n]*)")

def select(path: str, names: set[str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise SystemExit(1) from None
    for line in lines:
        if not line or line.startswith("#"):
            continue
        match = _ENTRY.fullmatch(line)
        if match is None:
            continue
        name, value = match.groups()
        if name not in names:
            continue
        if name in selected or not value or value != value.strip():
            raise SystemExit(1)
        selected[name] = value
    if selected.keys() != names:
        raise SystemExit(1)
    return selected

worker = select(
    worker_env_file,
    {
        "BIOCATALYST_R2_BUCKET",
        "BIOCATALYST_R2_ENDPOINT",
        "BIOCATALYST_R2_ACCESS_KEY_ID",
        "BIOCATALYST_R2_JURISDICTION",
    },
)
control = select(
    control_env_file,
    {
        "BIOCATALYST_R2_CONTROL_ACCOUNT_ID",
        "BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS",
        "BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS",
    },
)
result = subprocess.run(
    [
        python,
        "-m",
        "scripts.biocatalyst_activation",
        "--mode",
        "validate",
        "--gate-file",
        gate_file,
        "--heartbeat-file",
        heartbeat_file,
    ],
    cwd="/opt/macro",
    env={**worker, **control},
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    check=False,
)
raise SystemExit(result.returncode)
PY
}

verify_prereqs() {
	local key gate_id control_account_id
	local missing=()

	require_nonempty_keys "$ENV_FILE" "${required_env_keys[@]}"

	if ! grep -Eq '^BIOCATALYST_ENABLED=1([[:space:]]*)$' "$ENV_FILE"; then
		missing+=("BIOCATALYST_ENABLED must equal 1")
	fi
	if grep -Eq '^BIOCATALYST_PROSPECTIVE_ENABLED=' "$ENV_FILE" && \
		! grep -Eq '^BIOCATALYST_PROSPECTIVE_ENABLED=[01]([[:space:]]*)$' "$ENV_FILE"; then
		missing+=("BIOCATALYST_PROSPECTIVE_ENABLED must equal 0 or 1")
	fi
	if grep -Eq '^BIOCATALYST_R2_RETENTION_CONFIRMED=' "$ENV_FILE" && \
		! grep -Eq '^BIOCATALYST_R2_RETENTION_CONFIRMED=[01]([[:space:]]*)$' "$ENV_FILE"; then
		missing+=("BIOCATALYST_R2_RETENTION_CONFIRMED must equal 0 or 1")
	fi

	if grep -Eq '^BIOCATALYST_PROSPECTIVE_ENABLED=1([[:space:]]*)$' "$ENV_FILE"; then
		require_nonempty_keys "$ENV_FILE" BIOCATALYST_R2_ACTIVATION_ID
		if ! grep -Eq '^BIOCATALYST_R2_ACTIVATION_ID=r2_activation_[a-f0-9]{24}([[:space:]]*)$' "$ENV_FILE"; then
			missing+=("BIOCATALYST_R2_ACTIVATION_ID must be a canonical activation id when prospective collection is enabled")
		fi
		require_nonempty_keys "$ENV_FILE" BIOCATALYST_R2_ACCOUNT_ID
		if ! grep -Eq '^BIOCATALYST_R2_ACCOUNT_ID=[a-f0-9]{32}([[:space:]]*)$' "$ENV_FILE"; then
			missing+=("BIOCATALYST_R2_ACCOUNT_ID must be a canonical Cloudflare account id when prospective collection is enabled")
		fi
		require_nonempty_keys "$ENV_FILE" BIOCATALYST_R2_JURISDICTION
		if ! grep -Eq '^BIOCATALYST_R2_JURISDICTION=(default|eu|fedramp)([[:space:]]*)$' "$ENV_FILE"; then
			missing+=("BIOCATALYST_R2_JURISDICTION must be default, eu, or fedramp when prospective collection is enabled")
		fi
		require_nonempty_keys "$CONTROL_ENV_FILE" "${required_control_env_keys[@]}"
		if ! grep -Eq '^BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS=86400([[:space:]]*)$' "$CONTROL_ENV_FILE"; then
			missing+=("BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS must equal 86400")
		fi
		if ! grep -Eq '^BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS=7200([[:space:]]*)$' "$CONTROL_ENV_FILE"; then
			missing+=("BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS must equal 7200")
		fi
		if ! python3 "$SECURE_PATH_HELPER" verify-activation \
			--state-root "$STATE_ROOT" \
			--activation-root "$ACTIVATION_ROOT" \
			--activation-gate "$ACTIVATION_GATE" \
			--activation-heartbeat "$ACTIVATION_HEARTBEAT" \
			--control-env-file "$CONTROL_ENV_FILE" \
			--root-uid "$ROOT_UID" \
			--root-gid "$ROOT_GID" \
			--service-gid "$SERVICE_GID"; then
			missing+=("root-owned activation gate/control path verification")
		elif ! validate_activation_artifacts; then
			missing+=("cryptographically valid and fresh activation gate/heartbeat")
		elif ! gate_id="$(gate_activation_id)"; then
			missing+=("valid activation gate")
		elif ! grep -Eq "^BIOCATALYST_R2_ACTIVATION_ID=${gate_id}([[:space:]]*)$" "$ENV_FILE"; then
			missing+=("BIOCATALYST_R2_ACTIVATION_ID must match activation gate")
		elif ! grep -Eq '^BIOCATALYST_R2_CONTROL_ACCOUNT_ID=[a-f0-9]{32}([[:space:]]*)$' "$CONTROL_ENV_FILE"; then
			missing+=("BIOCATALYST_R2_CONTROL_ACCOUNT_ID must be a canonical Cloudflare account id")
		else
			control_account_id="$(sed -nE 's/^BIOCATALYST_R2_CONTROL_ACCOUNT_ID=([a-f0-9]{32})[[:space:]]*$/\1/p' "$CONTROL_ENV_FILE")"
			if ! grep -Eq "^BIOCATALYST_R2_ACCOUNT_ID=${control_account_id}([[:space:]]*)$" "$ENV_FILE"; then
				missing+=("BIOCATALYST_R2_ACCOUNT_ID must match the root-only control account")
			fi
		fi
	fi

	if [ "${#missing[@]}" -gt 0 ]; then
		log "prerequisites incomplete in $ENV_FILE: ${missing[*]}" >&2
		return 1
	fi

	log "root-owned BioCatalyst prerequisites verified"
}

verify_units() {
	if command -v systemd-analyze >/dev/null 2>&1; then
		systemd-analyze verify "$SERVICE_SOURCE" "$TIMER_SOURCE" \
			"$HEARTBEAT_SERVICE_SOURCE" "$HEARTBEAT_TIMER_SOURCE"
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
	[ -f "$HEARTBEAT_SERVICE_SOURCE" ] || die "missing heartbeat service source: $HEARTBEAT_SERVICE_SOURCE"
	[ -f "$HEARTBEAT_TIMER_SOURCE" ] || die "missing heartbeat timer source: $HEARTBEAT_TIMER_SOURCE"
	[ -f "$HEARTBEAT_RUNNER" ] || die "missing heartbeat runner: $HEARTBEAT_RUNNER"
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
		--control-env-file "$CONTROL_ENV_FILE" \
		--activation-root "$ACTIVATION_ROOT" \
		--activation-gate "$ACTIVATION_GATE" \
		--activation-heartbeat "$ACTIVATION_HEARTBEAT" \
		--service-uid "$SERVICE_UID" \
		--service-gid "$SERVICE_GID" \
		--root-uid "$ROOT_UID" \
		--root-gid "$ROOT_GID" \
		--env-uid "$ROOT_UID" \
		--env-gid "$ROOT_GID"

	if [ "$verify_only" -eq 1 ]; then
		verify_runtime
		verify_prereqs
		verify_units
		log "timer remains disabled; follow the operations runbook to arm it"
		exit 0
	fi

	install_runtime
	verify_units
	command -v systemctl >/dev/null 2>&1 || die "systemctl is required to install units"
	install -m 0644 "$SERVICE_SOURCE" "$SERVICE_DEST"
	install -m 0644 "$TIMER_SOURCE" "$TIMER_DEST"
	install -m 0644 "$HEARTBEAT_SERVICE_SOURCE" "$HEARTBEAT_SERVICE_DEST"
	install -m 0644 "$HEARTBEAT_TIMER_SOURCE" "$HEARTBEAT_TIMER_DEST"
	systemctl daemon-reload
	log "units installed, but intentionally left disabled"
	log "populate $ENV_FILE and root-only $CONTROL_ENV_FILE, run --verify-prereqs, then follow the operations runbook"
}

main "$@"
