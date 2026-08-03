#!/usr/bin/env bash
# Persist one root-only, read-only R2 retention heartbeat without exposing the
# control token to the collector. The activation module owns remote validation;
# this wrapper owns only a same-directory atomic local replacement.
set -euo pipefail

APP_DIR=/opt/macro
RUNTIME_PYTHON=/opt/macro-biocatalyst/current/bin/python
SECURE_PATH_HELPER="$APP_DIR/app/deploy/biocatalyst-secure-paths.py"
STATE_ROOT=/var/lib/macro-biocatalyst
ACTIVATION_ROOT=/var/lib/macro-biocatalyst/activation
ACTIVATION_GATE="$ACTIVATION_ROOT/gate.json"
HEARTBEAT_FILE="$ACTIVATION_ROOT/heartbeat.json"
CONTROL_ENV_FILE=/etc/macro-biocatalyst-control.env
SERVICE_GROUP=macro-biocatalyst

log() {
	echo "biocatalyst-activation-heartbeat: $*" >&2
}

die() {
	log "$*"
	exit 1
}

[ "$(id -u)" -eq 0 ] || die "must run as root"
[ "${BIOCATALYST_ACTIVATION_ROOT:-}" = "$ACTIVATION_ROOT" ] || \
	die "activation root must be the fixed control-plane path"
[ "${BIOCATALYST_R2_ACTIVATION_GATE_PATH:-}" = "$ACTIVATION_GATE" ] || \
	die "activation gate must be the fixed control-plane path"
[ "${BIOCATALYST_R2_ACTIVATION_HEARTBEAT_PATH:-}" = "$HEARTBEAT_FILE" ] || \
	die "activation heartbeat must be the fixed control-plane path"
[ -x "$RUNTIME_PYTHON" ] || die "isolated runtime Python is unavailable"
[ -f "$SECURE_PATH_HELPER" ] || die "secure path helper is unavailable"

SERVICE_GID="$(getent group "$SERVICE_GROUP" | awk -F: '{print $3}')"
[ -n "$SERVICE_GID" ] || die "service group is unavailable"
ROOT_UID="$(id -u root)"
ROOT_GID="$(id -g root)"
"$RUNTIME_PYTHON" "$SECURE_PATH_HELPER" verify-activation \
	--state-root "$STATE_ROOT" \
	--activation-root "$ACTIVATION_ROOT" \
	--activation-gate "$ACTIVATION_GATE" \
	--control-env-file "$CONTROL_ENV_FILE" \
	--root-uid "$ROOT_UID" \
	--root-gid "$ROOT_GID" \
	--service-gid "$SERVICE_GID"

temporary_heartbeat="$(mktemp "$ACTIVATION_ROOT/.heartbeat.XXXXXX")"
cleanup() {
	rm -f -- "$temporary_heartbeat"
}
trap cleanup EXIT

"$RUNTIME_PYTHON" -m scripts.biocatalyst_activation --mode heartbeat \
	--gate-file "$ACTIVATION_GATE" >"$temporary_heartbeat"
"$RUNTIME_PYTHON" - "$temporary_heartbeat" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
if not isinstance(payload, dict) or payload.get("contract_id") != "biocatalyst_activation_heartbeat.v1":
    raise SystemExit("activation heartbeat did not emit its canonical JSON contract")
PY

temporary_gid="$(stat -c '%g' "$temporary_heartbeat")"
[ "$temporary_gid" = "$SERVICE_GID" ] || die "heartbeat staging file has an unexpected group"
chmod 0440 "$temporary_heartbeat"
mv -f -- "$temporary_heartbeat" "$HEARTBEAT_FILE"
trap - EXIT
