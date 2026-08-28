#!/usr/bin/env bash
# Provision the M0D v2 SPY REST credential boundary.  The provider key is
# copied from existing private operator state only; it is never printed,
# exported, passed on argv, or read by the capture program from the process
# environment.
set -euo pipefail

CREDENTIAL_ROOT=/etc/macro-market-memory-spy-rest
CRED_FILE_A=$CREDENTIAL_ROOT/MASSIVE_API_KEY
CRED_FILE_B=$CREDENTIAL_ROOT/POLYGON_API_KEY

die() {
	printf 'market-memory-spy-rest-prereqs: %s\n' "$*" >&2
	exit 1
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
		case "$name" in
			MASSIVE_API_KEY|POLYGON_API_KEY) continue ;;
		esac
		[[ "$name" =~ ^\.spy-rest-api-key\.[A-Za-z0-9]{6}$ ]] || \
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
	local entry name count=0
	shopt -s nullglob dotglob
	for entry in "$CREDENTIAL_ROOT"/*; do
		count=$((count + 1))
		[ "$count" -le 16 ] || return 1
		name=${entry##*/}
		case "$name" in
			MASSIVE_API_KEY|POLYGON_API_KEY) ;;
			*) return 1 ;;
		esac
	done
	shopt -u nullglob dotglob
}

write_credential_file() {
	local dest=$1 candidate=$2
	local tmp file_metadata final_candidate file_lines file_size compare_status
	[ ! -L "$dest" ] || die "credential file must not be a symlink: ${dest##*/}"
	tmp=$(mktemp "$CREDENTIAL_ROOT/.spy-rest-api-key.XXXXXX") || \
		die "cannot create temporary credential"
	printf '%s\n' "$candidate" >"$tmp" || {
		rm -f "$tmp" || true
		die "cannot write temporary credential"
	}
	chown root:root "$tmp" || die "cannot set temporary credential owner"
	chmod 0400 "$tmp" || die "cannot set temporary credential mode"
	if [ ! -e "$dest" ]; then
		mv -f "$tmp" "$dest" || die "cannot create derived credential: ${dest##*/}"
	else
		[ -f "$dest" ] && [ ! -L "$dest" ] || \
			die "existing derived credential is not a regular file: ${dest##*/}"
		compare_status=0
		cmp -s "$tmp" "$dest" || compare_status=$?
		if [ "$compare_status" -eq 0 ]; then
			rm -f "$tmp" || die "cannot remove unchanged temporary credential"
		elif [ "$compare_status" -eq 1 ]; then
			mv -f "$tmp" "$dest" || die "cannot atomically replace credential: ${dest##*/}"
		else
			rm -f "$tmp" || true
			die "cannot compare credential state: ${dest##*/}"
		fi
	fi
	[ -f "$dest" ] && [ ! -L "$dest" ] || die "derived credential is not a regular file: ${dest##*/}"
	chown root:root "$dest" || die "cannot set credential owner: ${dest##*/}"
	chmod 0400 "$dest" || die "cannot set credential mode: ${dest##*/}"
	file_metadata=$(stat -c '%U:%G:%a' "$dest") || \
		die "cannot inspect credential file: ${dest##*/}"
	[ "$file_metadata" = 'root:root:400' ] || \
		die "credential must be root:root mode 0400: ${dest##*/}"
	file_size=$(stat -c '%s' "$dest") || die "cannot inspect credential byte length"
	file_lines=$(wc -l <"$dest") || die "cannot inspect credential lines"
	final_candidate=$(sed -n '1p' "$dest") || die "cannot read final credential"
	[ "$file_lines" -eq 1 ] && \
		[ "$file_size" -eq "$(( ${#final_candidate} + 1 ))" ] && \
		[ "${#final_candidate}" -ge 16 ] && [ "${#final_candidate}" -le 512 ] || \
		die "final credential has invalid byte shape: ${dest##*/}"
	case "$final_candidate" in
		*[!A-Za-z0-9._-]*) die "final credential contains invalid bytes: ${dest##*/}" ;;
	esac
	unset final_candidate
}

provision_credential() {
	local candidate='' source extract_status root_metadata
	[ ! -L "$CREDENTIAL_ROOT" ] || die "credential root must not be a symlink"
	install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT" || \
		die "cannot provision credential root"
	[ -d "$CREDENTIAL_ROOT" ] || die "credential root must be a real directory"
	root_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_ROOT") || \
		die "cannot inspect credential root"
	[ "$root_metadata" = 'root:root:700' ] || \
		die "credential root must be root:root mode 0700"
	cleanup_credential_temps
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
		# Do not delete already-provisioned files. A later extract miss
		# (mode/form/absent source) must not wipe a working LoadCredential
		# pair that the 04:00Z oneshot still needs.
		printf '%s\n' 'market-memory-spy-rest-prereqs: no extractable key in operator env files' >&2
		return 2
	fi
	write_credential_file "$CRED_FILE_A" "$candidate"
	write_credential_file "$CRED_FILE_B" "$candidate"
	unset candidate
}

check_ready() {
	local source extract_status candidate='' file_metadata file_lines file_size final_candidate
	local root_metadata dest
	[ ! -L "$CREDENTIAL_ROOT" ] || die "credential root must not be a symlink"
	[ -d "$CREDENTIAL_ROOT" ] || return 2
	root_metadata=$(stat -c '%U:%G:%a' "$CREDENTIAL_ROOT") || \
		die "cannot inspect credential root"
	[ "$root_metadata" = 'root:root:700' ] || return 2
	credential_root_contains_only_final || return 2
	for dest in "$CRED_FILE_A" "$CRED_FILE_B"; do
		[ ! -L "$dest" ] || die "credential file must not be a symlink: ${dest##*/}"
		[ -f "$dest" ] || return 2
		file_metadata=$(stat -c '%U:%G:%a' "$dest") || \
			die "cannot inspect credential file: ${dest##*/}"
		[ "$file_metadata" = 'root:root:400' ] || return 2
		file_size=$(stat -c '%s' "$dest") || die "cannot inspect credential byte length"
		file_lines=$(wc -l <"$dest") || die "cannot inspect credential lines"
		final_candidate=$(sed -n '1p' "$dest") || die "cannot read final credential"
		[ "$file_lines" -eq 1 ] && \
			[ "$file_size" -eq "$(( ${#final_candidate} + 1 ))" ] && \
			[ "${#final_candidate}" -ge 16 ] && [ "${#final_candidate}" -le 512 ] || \
			return 2
		case "$final_candidate" in
			*[!A-Za-z0-9._-]*) return 2 ;;
		esac
		unset final_candidate
	done
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
	for dest in "$CRED_FILE_A" "$CRED_FILE_B"; do
		final_candidate=$(sed -n '1p' "$dest") || die "cannot read final credential"
		[ "$candidate" = "$final_candidate" ] || return 2
		unset final_candidate
	done
	unset candidate
}

main() {
	[ "$(id -u)" -eq 0 ] || die "must run as root"
	if [ "${1:-}" = '--check-ready' ]; then
		[ "$#" -eq 1 ] || die "check-ready mode accepts no additional arguments"
		check_ready
		return $?
	fi
	[ "$#" -eq 0 ] || die "unexpected argument"
	if provision_credential; then
		printf '%s\n' 'market-memory-spy-rest-prereqs: credential ready'
	else
		printf '%s\n' 'market-memory-spy-rest-prereqs: credential absent; lane remains disarmed' >&2
		return 2
	fi
}

main "$@"
