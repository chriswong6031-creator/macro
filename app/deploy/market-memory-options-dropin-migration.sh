#!/usr/bin/env bash
# One-time, fail-closed migration for the reviewed legacy macro-api Ollama
# drop-in.  The canonical unit now owns the same optional EnvironmentFile line,
# so keeping the historical drop-in would make exact loaded-unit attestation
# reject an otherwise safe production API boundary.

MM_LEGACY_API_DROPIN_DIR=/etc/systemd/system/macro-api.service.d
MM_LEGACY_API_DROPIN=$MM_LEGACY_API_DROPIN_DIR/ollama.conf
MM_LEGACY_API_DROPIN_SHA256=872c37b9280aa4ab129139c021144242dd62c05c4a736f5541e8b20caec90f91

mm_remove_exact_legacy_api_ollama_dropin() {
	local directory_metadata dropin_metadata dropin_sha256 entry
	local -a entries

	[ -d "$MM_LEGACY_API_DROPIN_DIR" ] && \
		[ ! -L "$MM_LEGACY_API_DROPIN_DIR" ] || return 1
	directory_metadata=$(stat -c '%U:%G:%a' "$MM_LEGACY_API_DROPIN_DIR") || return 1
	[ "$directory_metadata" = root:root:755 ] || return 1

	entries=()
	for entry in \
		"$MM_LEGACY_API_DROPIN_DIR"/* \
		"$MM_LEGACY_API_DROPIN_DIR"/.[!.]* \
		"$MM_LEGACY_API_DROPIN_DIR"/..?*
	do
		if [ -e "$entry" ] || [ -L "$entry" ]; then
			entries+=("$entry")
		fi
	done
	[ "${#entries[@]}" -eq 1 ] && \
		[ "${entries[0]}" = "$MM_LEGACY_API_DROPIN" ] || return 1
	[ -f "$MM_LEGACY_API_DROPIN" ] && \
		[ ! -L "$MM_LEGACY_API_DROPIN" ] || return 1
	dropin_metadata=$(stat -c '%U:%G:%a' "$MM_LEGACY_API_DROPIN") || return 1
	[ "$dropin_metadata" = root:root:644 ] || return 1
	[ "$(stat -c '%s' "$MM_LEGACY_API_DROPIN")" = 49 ] || return 1
	dropin_sha256=$(sha256sum "$MM_LEGACY_API_DROPIN" | awk '{print $1}') || return 1
	[ "$dropin_sha256" = "$MM_LEGACY_API_DROPIN_SHA256" ] || return 1

	rm -f -- "$MM_LEGACY_API_DROPIN" || return 1
	rmdir -- "$MM_LEGACY_API_DROPIN_DIR" || return 1
}
