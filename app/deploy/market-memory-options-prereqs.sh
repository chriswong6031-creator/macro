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

validate_service_identity() {
	local passwd_entry account_name account_home account_shell account_uid account_gid
	local expected_gid all_groups
	account_uid=$(id -u "$SERVICE_USER") || die "cannot inspect service uid"
	account_gid=$(id -g "$SERVICE_USER") || die "cannot inspect service gid"
	expected_gid=$(getent group "$SERVICE_GROUP" | awk -F: '{print $3}') || \
		die "cannot inspect service group"
	[ "$account_uid" -ne 0 ] || die "$SERVICE_USER must not be uid 0"
	[ "$account_gid" -ne 0 ] || die "$SERVICE_USER must not use gid 0"
	[ "$account_gid" = "$expected_gid" ] || \
		die "$SERVICE_USER must use $SERVICE_GROUP as its primary group"
	all_groups=$(id -G "$SERVICE_USER") || die "cannot inspect supplementary groups"
	[ "$all_groups" = "$account_gid" ] || \
		die "$SERVICE_USER must have no supplementary groups"
	passwd_entry="$(getent passwd "$SERVICE_USER")" || die "cannot inspect $SERVICE_USER"
	IFS=: read -r account_name _ _ _ _ account_home account_shell <<<"$passwd_entry"
	[ "$account_name" = "$SERVICE_USER" ] || die "unexpected service identity"
	[ "$account_home" = "$STATE_ROOT" ] || die "$SERVICE_USER has an unexpected home"
	case "$account_shell" in
		*/nologin|*/false) ;;
		*) die "$SERVICE_USER must use a non-login shell" ;;
	esac
}

ensure_service_identity() {
	if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
		groupadd --system "$SERVICE_GROUP" || die "cannot create service group"
	fi
	if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
		useradd --system --gid "$SERVICE_GROUP" --home-dir "$STATE_ROOT" \
			--no-create-home --shell /usr/sbin/nologin "$SERVICE_USER" || \
			die "cannot create service identity"
	fi
	validate_service_identity
}

validate_deny_anchors() {
	local state_metadata credential_metadata
	[ ! -L "$STATE_ROOT" ] || die "state parent must not be a symlink"
	[ -d "$STATE_ROOT" ] || die "state deny anchor must be a real directory"
	state_metadata=$(stat -c '%U:%G:%a' "$STATE_ROOT") || \
		die "cannot inspect state deny anchor"
	case "$state_metadata" in
		root:root:700|"root:$SERVICE_GROUP:710") ;;
		*) die "state deny anchor has unsafe ownership or mode" ;;
	esac

	[ ! -L "$CREDENTIAL_ROOT" ] || die "credential root must not be a symlink"
	[ -d "$CREDENTIAL_ROOT" ] || \
		die "credential deny anchor must be a real directory"
	credential_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_ROOT") || \
		die "cannot inspect credential deny anchor"
	[ "$credential_metadata" = 'root:root:700' ] || \
		die "credential deny anchor must be root:root mode 0700"
}

ensure_deny_anchors() {
	# Nonoptional InaccessiblePaths require their targets to exist before the
	# first API/MM service restart.  Identity-only mode creates only empty,
	# root-owned anchors—never the service-writable profile or credential file.
	[ ! -L "$STATE_ROOT" ] || die "state parent must not be a symlink"
	if [ ! -e "$STATE_ROOT" ]; then
		install -d -o root -g root -m 0700 "$STATE_ROOT" || \
			die "cannot provision empty state deny anchor"
	fi
	[ ! -L "$CREDENTIAL_ROOT" ] || die "credential root must not be a symlink"
	if [ ! -e "$CREDENTIAL_ROOT" ]; then
		install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT" || \
			die "cannot provision empty credential deny anchor"
	fi
	validate_deny_anchors
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

cleanup_credential_temps() {
	local entry name owner mode size count=0
	shopt -s nullglob dotglob
	for entry in "$CREDENTIAL_ROOT"/*; do
		count=$((count + 1))
		[ "$count" -le 16 ] || die "credential root contains too many entries"
		name=${entry##*/}
		if [ "$name" = "${CREDENTIAL_FILE##*/}" ]; then
			continue
		fi
		[[ "$name" =~ ^\.massive-option-oi-api-key\.[A-Za-z0-9]{6}$ ]] || \
			die "credential root contains an unknown entry"
		[ -f "$entry" ] && [ ! -L "$entry" ] || \
			die "credential temporary entry is not a regular file"
		owner=$(stat -c '%U' "$entry") || die "cannot inspect credential temporary owner"
		mode=$(stat -c '%a' "$entry") || die "cannot inspect credential temporary mode"
		size=$(stat -c '%s' "$entry") || die "cannot inspect credential temporary size"
		[ "$owner" = root ] || die "credential temporary entry is not root-owned"
		case "$mode" in
			600|400) ;;
			*) die "credential temporary entry has an unsafe mode" ;;
		esac
		[ "$size" -le 513 ] || die "credential temporary entry is oversized"
		rm -f "$entry" || die "cannot remove orphan credential temporary"
	done
	shopt -u nullglob dotglob
}

credential_root_contains_only_final() {
	local entry count=0
	shopt -s nullglob dotglob
	for entry in "$CREDENTIAL_ROOT"/*; do
		count=$((count + 1))
		[ "$count" -le 16 ] || return 1
		[ "${entry##*/}" = "${CREDENTIAL_FILE##*/}" ] || return 1
	done
	shopt -u nullglob dotglob
}

provision_credential() {
	local candidate='' source tmp root_metadata file_metadata compare_status extract_status
	local final_candidate file_lines file_size
	[ ! -L "$CREDENTIAL_ROOT" ] || die "credential root must not be a symlink"
	install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT" || \
		die "cannot provision credential root"
	[ -d "$CREDENTIAL_ROOT" ] || die "credential root must be a real directory"
	root_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_ROOT") || \
		die "cannot inspect credential root"
	[ "$root_metadata" = 'root:root:700' ] || \
		die "credential root must be root:root mode 0700"
	cleanup_credential_temps
	[ ! -L "$CREDENTIAL_FILE" ] || die "credential source must not be a symlink"
	for source in /opt/macro/.env /etc/macro-api.env /etc/macro-live.env; do
		extract_status=0
		candidate=$(extract_private_key "$source") || extract_status=$?
		if [ "$extract_status" -eq 0 ]; then
			break
		elif [ "$extract_status" -ne 2 ]; then
			die "cannot inspect private credential source"
		fi
	done
	if [ -z "$candidate" ]; then
		if [ -e "$CREDENTIAL_FILE" ] || [ -L "$CREDENTIAL_FILE" ]; then
			[ -f "$CREDENTIAL_FILE" ] && [ ! -L "$CREDENTIAL_FILE" ] || \
				die "derived credential is not a removable regular file"
			rm -f "$CREDENTIAL_FILE" || die "cannot remove stale derived credential"
		fi
		return 2
	fi

	tmp=$(mktemp "$CREDENTIAL_ROOT/.massive-option-oi-api-key.XXXXXX") || \
		die "cannot create temporary credential"
	printf '%s\n' "$candidate" >"$tmp" || {
		rm -f "$tmp" || true
		die "cannot write temporary credential"
	}
	unset candidate
	chown root:root "$tmp" || die "cannot set temporary credential owner"
	chmod 0400 "$tmp" || die "cannot set temporary credential mode"
	if [ ! -e "$CREDENTIAL_FILE" ]; then
		mv -f "$tmp" "$CREDENTIAL_FILE" || die "cannot create derived credential"
	else
		[ -f "$CREDENTIAL_FILE" ] && [ ! -L "$CREDENTIAL_FILE" ] || \
			die "existing derived credential is not a regular file"
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
	[ -f "$CREDENTIAL_FILE" ] && [ ! -L "$CREDENTIAL_FILE" ] || \
		die "derived credential is not a regular file"
	chown root:root "$CREDENTIAL_FILE" || die "cannot set credential owner"
	chmod 0400 "$CREDENTIAL_FILE" || die "cannot set credential mode"
	file_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_FILE") || \
		die "cannot inspect credential file"
	[ "$file_metadata" = 'root:root:400' ] || \
		die "credential source must be root:root mode 0400"
	file_size=$(stat -c '%s' "$CREDENTIAL_FILE") || \
		die "cannot inspect credential byte length"
	file_lines=$(wc -l <"$CREDENTIAL_FILE") || die "cannot inspect credential lines"
	final_candidate=$(sed -n '1p' "$CREDENTIAL_FILE") || \
		die "cannot read final credential"
	[ "$file_lines" -eq 1 ] && \
		[ "$file_size" -eq "$(( ${#final_candidate} + 1 ))" ] && \
		[ "${#final_candidate}" -ge 16 ] && [ "${#final_candidate}" -le 512 ] || \
		die "final credential has invalid byte shape"
	case "$final_candidate" in
		*[!A-Za-z0-9._-]*) die "final credential contains invalid bytes" ;;
	esac
	unset final_candidate
}

provision_state_root() {
	# The service may write the exact profile, never its parent.  Keeping the
	# parent root-owned prevents the service identity from swapping options-v1
	# for a symlink before a later privileged updater pass.
	[ ! -L "$STATE_ROOT" ] || die "state parent must not be a symlink"
	install -d -o root -g "$SERVICE_GROUP" -m 0710 "$STATE_ROOT" || \
		die "cannot provision state parent"
	[ ! -L "$STORE_ROOT" ] || die "options-v1 root must not be a symlink"
	install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$STORE_ROOT" || \
		die "cannot provision options-v1 root"
	local state_metadata store_metadata
	state_metadata=$(stat -c '%U:%G:%a' "$STATE_ROOT") || \
		die "cannot inspect state parent"
	store_metadata=$(stat -c '%U:%G:%a' "$STORE_ROOT") || \
		die "cannot inspect options-v1 root"
	[ "$state_metadata" = "root:$SERVICE_GROUP:710" ] || \
		die "state parent must be root-owned mode 0710"
	[ "$store_metadata" = "$SERVICE_USER:$SERVICE_GROUP:700" ] || \
		die "options-v1 root must be service-owned mode 0700"
}

check_full_ready() {
	local candidate='' source extract_status file_metadata file_lines file_size
	local final_candidate
	[ ! -L "$STATE_ROOT" ] && [ -d "$STATE_ROOT" ] || \
		die "state parent is not a real directory"
	credential_root_contains_only_final || return 2
	[ "$(stat -c '%U:%G:%a' "$STATE_ROOT")" = "root:$SERVICE_GROUP:710" ] || \
		return 2
	[ ! -L "$STORE_ROOT" ] || die "options-v1 root must not be a symlink"
	[ -d "$STORE_ROOT" ] || return 2
	[ "$(stat -c '%U:%G:%a' "$STORE_ROOT")" = "$SERVICE_USER:$SERVICE_GROUP:700" ] || \
		return 2
	[ ! -L "$CREDENTIAL_FILE" ] || die "credential source must not be a symlink"
	[ -f "$CREDENTIAL_FILE" ] || return 2
	file_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_FILE") || \
		die "cannot inspect credential file"
	[ "$file_metadata" = 'root:root:400' ] || return 2
	for source in /opt/macro/.env /etc/macro-api.env /etc/macro-live.env; do
		extract_status=0
		candidate=$(extract_private_key "$source") || extract_status=$?
		if [ "$extract_status" -eq 0 ]; then
			break
		elif [ "$extract_status" -ne 2 ]; then
			die "cannot inspect private credential source"
		fi
	done
	[ -n "$candidate" ] || return 2
	file_size=$(stat -c '%s' "$CREDENTIAL_FILE") || \
		die "cannot inspect credential byte length"
	file_lines=$(wc -l <"$CREDENTIAL_FILE") || die "cannot inspect credential lines"
	final_candidate=$(sed -n '1p' "$CREDENTIAL_FILE") || \
		die "cannot read final credential"
	[ "$file_lines" -eq 1 ] && \
		[ "$file_size" -eq "$(( ${#final_candidate} + 1 ))" ] && \
		[ "${#final_candidate}" -ge 16 ] && [ "${#final_candidate}" -le 512 ] || \
		return 2
	case "$final_candidate" in
		*[!A-Za-z0-9._-]*) return 2 ;;
	esac
	[ "$candidate" = "$final_candidate" ] || return 2
	unset candidate final_candidate
}

main() {
	[ "$(id -u)" -eq 0 ] || die "must run as root"
	if [ "${1:-}" = '--check-identity-only' ]; then
		[ "$#" -eq 1 ] || die "check-identity-only mode accepts no additional arguments"
		validate_service_identity
		validate_deny_anchors
		return 0
	fi
	ensure_service_identity
	ensure_deny_anchors
	if [ "${1:-}" = '--identity-only' ]; then
		[ "$#" -eq 1 ] || die "identity-only mode accepts no additional arguments"
		return 0
	fi
	if [ "${1:-}" = '--check-ready' ]; then
		[ "$#" -eq 1 ] || die "check-ready mode accepts no additional arguments"
		check_full_ready
		return $?
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
