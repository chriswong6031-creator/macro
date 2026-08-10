#!/usr/bin/env bash
# Provision the disjoint W1B.5 option-OI canary identity, private root, and
# systemd credential source.  The provider key is copied from existing private
# operator state only; it is never printed, exported, passed on argv, or read by
# the capture program from the process environment.
set -euo pipefail

SERVICE_USER=macro-market-memory-options
SERVICE_GROUP=macro-market-memory-options
STATE_ROOT=/var/lib/macro-market-memory-options
STORE_ROOT=$STATE_ROOT/options-v1
CREDENTIAL_ROOT=/etc/macro-market-memory-options
CREDENTIAL_FILE=$CREDENTIAL_ROOT/massive-option-oi-api-key

die() {
	printf 'market-memory-options-prereqs: %s\n' "$*" >&2
	exit 1
}

ensure_service_identity() {
	local passwd_entry account_name account_home account_shell
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
	IFS=: read -r account_name _ _ _ _ account_home account_shell <<<"$passwd_entry"
	[ "$account_name" = "$SERVICE_USER" ] || die "unexpected service identity"
	[ "$account_home" = "$STATE_ROOT" ] || die "$SERVICE_USER has an unexpected home"
	case "$account_shell" in
		*/nologin|*/false) ;;
		*) die "$SERVICE_USER must use a non-login shell" ;;
	esac
}

extract_private_key() {
	local source=$1 candidate mode owner
	[ -e "$source" ] || return 2
	[ -f "$source" ] && [ ! -L "$source" ] || return 2
	owner=$(stat -c '%U' "$source") || die "cannot inspect credential source owner"
	[ "$owner" = root ] || return 2
	mode=$(stat -c '%a' "$source") || die "cannot inspect credential source mode"
	[ "${mode: -2}" = 00 ] || return 2
	candidate=$(awk '
		/^[[:space:]]*MASSIVE_API_KEY=/ {
			sub(/^[^=]*=/, ""); sub(/\r$/, ""); print; exit
		}
	' "$source") || die "cannot read private credential source"
	if [ -z "$candidate" ]; then
		candidate=$(awk '
			/^[[:space:]]*POLYGON_API_KEY=/ {
				sub(/^[^=]*=/, ""); sub(/\r$/, ""); print; exit
			}
		' "$source") || die "cannot read private credential source"
	fi
	case "$candidate" in
		\"*\") candidate=${candidate#\"}; candidate=${candidate%\"} ;;
		\'*\') candidate=${candidate#\'}; candidate=${candidate%\'} ;;
	esac
	[ "${#candidate}" -ge 16 ] && [ "${#candidate}" -le 512 ] || return 2
	case "$candidate" in
		*[!A-Za-z0-9._-]*) return 2 ;;
	esac
	printf '%s' "$candidate" || die "cannot return private credential value"
}

provision_credential() {
	local candidate='' source tmp root_metadata file_metadata compare_status extract_status
	[ ! -L "$CREDENTIAL_ROOT" ] || die "credential root must not be a symlink"
	install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT" || \
		die "cannot provision credential root"
	[ -d "$CREDENTIAL_ROOT" ] || die "credential root must be a real directory"
	root_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_ROOT") || \
		die "cannot inspect credential root"
	[ "$root_metadata" = 'root:root:700' ] || \
		die "credential root must be root:root mode 0700"
	[ ! -L "$CREDENTIAL_FILE" ] || die "credential source must not be a symlink"
	for source in /opt/macro/.env /etc/macro-api.env; do
		extract_status=0
		candidate=$(extract_private_key "$source") || extract_status=$?
		if [ "$extract_status" -eq 0 ]; then
			break
		elif [ "$extract_status" -ne 2 ]; then
			die "cannot inspect private credential source"
		fi
	done
	if [ -n "$candidate" ]; then
		tmp=$(mktemp "$CREDENTIAL_ROOT/.massive-option-oi-api-key.XXXXXX") || \
			die "cannot create temporary credential"
		printf '%s\n' "$candidate" >"$tmp" || {
			rm -f "$tmp" || true
			die "cannot write temporary credential"
		}
		unset candidate
		chown root:root "$tmp" || die "cannot set temporary credential owner"
		chmod 0400 "$tmp" || die "cannot set temporary credential mode"
		compare_status=0
		cmp -s "$tmp" "$CREDENTIAL_FILE" || compare_status=$?
		if [ "$compare_status" -eq 0 ]; then
			rm -f "$tmp" || die "cannot remove unchanged temporary credential"
		elif [ "$compare_status" -eq 1 ]; then
			mv -f "$tmp" "$CREDENTIAL_FILE" || die "cannot atomically replace credential"
		else
			rm -f "$tmp" || true
			die "cannot compare credential state"
		fi
	fi
	[ -f "$CREDENTIAL_FILE" ] || return 2
	chown root:root "$CREDENTIAL_FILE" || die "cannot set credential owner"
	chmod 0400 "$CREDENTIAL_FILE" || die "cannot set credential mode"
	file_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_FILE") || \
		die "cannot inspect credential file"
	[ "$file_metadata" = 'root:root:400' ] || \
		die "credential source must be root:root mode 0400"
}

provision_state_root() {
	# The service may write the exact profile, never its parent.  Keeping the
	# parent root-owned prevents the service identity from swapping options-v1
	# for a symlink before a later privileged updater pass.
	[ ! -L "$STATE_ROOT" ] || die "state parent must not be a symlink"
	install -d -o root -g "$SERVICE_GROUP" -m 0710 "$STATE_ROOT"
	[ ! -L "$STORE_ROOT" ] || die "options-v1 root must not be a symlink"
	install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$STORE_ROOT"
	[ "$(stat -c '%U:%G:%a' "$STATE_ROOT")" = "root:$SERVICE_GROUP:710" ] || \
		die "state parent must be root-owned mode 0710"
	[ "$(stat -c '%U:%G:%a' "$STORE_ROOT")" = "$SERVICE_USER:$SERVICE_GROUP:700" ] || \
		die "options-v1 root must be service-owned mode 0700"
}

main() {
	[ "$(id -u)" -eq 0 ] || die "must run as root"
	ensure_service_identity
	if [ "${1:-}" = '--identity-only' ]; then
		[ "$#" -eq 1 ] || die "identity-only mode accepts no additional arguments"
		return 0
	fi
	[ "$#" -eq 0 ] || die "unexpected argument"
	provision_state_root
	if provision_credential; then
		printf '%s\n' 'market-memory-options-prereqs: credential ready'
	else
		printf '%s\n' 'market-memory-options-prereqs: credential absent; lane remains disarmed' >&2
		return 2
	fi
}

main "$@"
