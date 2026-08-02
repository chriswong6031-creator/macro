#!/usr/bin/env bash
# Build and publish the isolated BioCatalyst Python runtime transactionally.
#
# Every dependency change is installed into a new versioned virtualenv.  The
# stable `current` symlink advances only after the candidate passes the runtime
# capability check, so a failed install cannot damage the last-good runtime.
set -euo pipefail

SERVICE_USER=macro-biocatalyst
SERVICE_GROUP=macro-biocatalyst
RUNTIME_ROOT=/opt/macro-biocatalyst
RUNTIMES_ROOT="$RUNTIME_ROOT/runtimes"
CURRENT_LINK="$RUNTIME_ROOT/current"
RUNTIME_LOCK="$RUNTIME_ROOT/.runtime-install.lock"
DEFAULT_REQUIREMENTS=/opt/macro/app/deploy/biocatalyst-requirements.txt
SECURE_PATH_HELPER=/opt/macro/app/deploy/biocatalyst-secure-paths.py

log() {
	echo "biocatalyst-runtime: $*"
}

die() {
	log "$*" >&2
	exit 1
}

usage() {
	cat <<'USAGE'
Usage: biocatalyst-runtime.sh --install [requirements-file]
       biocatalyst-runtime.sh --verify

--install builds and verifies a new immutable, versioned virtualenv when the
requirements hash differs or the current runtime is invalid.  It atomically
switches /opt/macro-biocatalyst/current only after verification.

--verify validates the already-published current runtime without changing it.
USAGE
}

require_identity() {
	getent group "$SERVICE_GROUP" >/dev/null 2>&1 || \
		die "missing service group: $SERVICE_GROUP (run biocatalyst-setup.sh)"
	id -u "$SERVICE_USER" >/dev/null 2>&1 || \
		die "missing service user: $SERVICE_USER (run biocatalyst-setup.sh)"
	[ "$(id -g "$SERVICE_USER")" = "$(getent group "$SERVICE_GROUP" | awk -F: '{print $3}')" ] || \
		die "$SERVICE_USER must use $SERVICE_GROUP as its primary group"
}

resolve_runtime() {
	local runtime_path
	[ -L "$CURRENT_LINK" ] || {
		log "current runtime pointer is missing or is not a symlink" >&2
		return 1
	}
	runtime_path="$(readlink -f -- "$CURRENT_LINK")" || {
		log "current runtime pointer cannot be resolved" >&2
		return 1
	}
	case "$runtime_path" in
		"$RUNTIMES_ROOT"/*) ;;
		*) log "current runtime pointer escapes $RUNTIMES_ROOT" >&2; return 1 ;;
	esac
	[ -d "$runtime_path" ] || {
		log "current runtime target is missing" >&2
		return 1
	}
	printf '%s\n' "$runtime_path"
}

verify_runtime_path() {
	local runtime_path="$1"
	local current_link="${2:-}"
	local verify_args=(
		verify-runtime
		--runtime-root "$RUNTIME_ROOT"
		--runtime-path "$runtime_path"
		--owner-uid "$(id -u root)"
		--service-gid "$(id -g "$SERVICE_USER")"
	)
	if [ -n "$current_link" ]; then
		verify_args+=(--current-link "$current_link")
	fi
	python3 "$SECURE_PATH_HELPER" "${verify_args[@]}" || return 1
	"$runtime_path/bin/python" -c '
import boto3  # noqa: F401
from botocore.session import get_session
members = get_session().get_service_model("s3").operation_model("PutObject").input_shape.members
assert "IfNoneMatch" in members, "botocore lacks PutObject.IfNoneMatch"
' || {
		log "runtime lacks immutable PutObject.IfNoneMatch support: $runtime_path" >&2
		return 1
	}
}

verify_current() {
	local runtime_path
	runtime_path="$(resolve_runtime)" || die "current runtime resolution failed"
	verify_runtime_path "$runtime_path" "$CURRENT_LINK" || die "current runtime verification failed"
	log "current runtime supports immutable R2 conditional creation"
}

install_runtime() {
	local requirements_source="$1"
	local requirements_hash installed_hash runtime_path
	local staging_runtime final_runtime next_link

	command -v python3 >/dev/null 2>&1 || die "python3 is required to create the isolated runtime"
	[ -f "$requirements_source" ] || die "missing BioCatalyst requirements: $requirements_source"
	requirements_hash="$(sha256sum "$requirements_source" | awk '{print $1}')"

	if [ -L "$CURRENT_LINK" ] && runtime_path="$(resolve_runtime)"; then
		if verify_runtime_path "$runtime_path" "$CURRENT_LINK"; then
			installed_hash="$(awk 'NR == 1 { print $1 }' "$runtime_path/.requirements.sha256")"
			if [ "$requirements_hash" = "$installed_hash" ]; then
				log "current runtime already matches the reviewed requirements"
				return 0
			fi
		fi
	fi

	staging_runtime="$(mktemp -d "$RUNTIMES_ROOT/.build-${requirements_hash}.XXXXXX")"
	next_link="$RUNTIME_ROOT/.current.$$"

	cleanup() {
		if [ -n "${staging_runtime:-}" ] && [ -d "$staging_runtime" ]; then
			rm -rf -- "$staging_runtime"
		fi
		if [ -n "${next_link:-}" ] && [ -L "$next_link" ]; then
			rm -f -- "$next_link"
		fi
	}
	trap cleanup EXIT

	python3 -m venv --copies "$staging_runtime"
	"$staging_runtime/bin/pip" install --disable-pip-version-check --upgrade pip
	"$staging_runtime/bin/pip" install --disable-pip-version-check -r "$requirements_source"
	printf '%s\n' "$requirements_hash" >"$staging_runtime/.requirements.sha256"
	chmod 0640 "$staging_runtime/.requirements.sha256"

	# Root owns the immutable runtime.  The service group can traverse and read
	# it, but cannot mutate packages or the publication pointer.
	chown -hR root:"$SERVICE_GROUP" "$staging_runtime"
	chmod -R g+rX,o-rwx "$staging_runtime"
	verify_runtime_path "$staging_runtime" || die "candidate runtime verification failed"
	final_runtime="$RUNTIMES_ROOT/${requirements_hash}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
	mv -T "$staging_runtime" "$final_runtime"
	staging_runtime=""

	ln -s "$final_runtime" "$next_link"
	chown -h root:"$SERVICE_GROUP" "$next_link"
	verify_runtime_path "$final_runtime" "$next_link" || die "runtime pointer verification failed"
	# Same-filesystem rename is the only operation that advances the runtime.
	# A failed build or verification leaves CURRENT_LINK untouched.
	mv -Tf "$next_link" "$CURRENT_LINK"
	next_link=""
	log "published verified runtime $requirements_hash"
}

main() {
	local mode="${1:-}"
	local requirements_source="${2:-$DEFAULT_REQUIREMENTS}"

	[ "$(id -u)" -eq 0 ] || die "must run as root"
	require_identity
	[ -f "$SECURE_PATH_HELPER" ] || die "missing secure path helper: $SECURE_PATH_HELPER"
	command -v python3 >/dev/null 2>&1 || die "python3 is required for secure runtime verification"
	python3 "$SECURE_PATH_HELPER" provision-runtime \
		--runtime-root "$RUNTIME_ROOT" \
		--owner-uid "$(id -u root)" \
		--service-gid "$(id -g "$SERVICE_USER")"
	command -v flock >/dev/null 2>&1 || die "flock is required for runtime serialization"
	exec 9>"$RUNTIME_LOCK"
	flock -x 9
	case "$mode" in
		--install) install_runtime "$requirements_source" ;;
		--verify) verify_current ;;
		--help|-h) usage ;;
		*) usage >&2; die "expected --install or --verify" ;;
	esac
}

main "$@"
