#!/usr/bin/env bash
# Read-only helpers for attesting the exact loaded systemd boundary used by the
# W1B.5 option-OI lane. Callers decide whether to repair or remain disarmed.

mm_reviewed_unit_file_ready() {
	local source=$1 installed=$2 metadata
	[ -f "$source" ] && [ ! -L "$source" ] || return 1
	[ -f "$installed" ] && [ ! -L "$installed" ] || return 1
	metadata=$(stat -c '%U:%G:%a' "$installed") || return 1
	[ "$metadata" = root:root:644 ] || return 1
	cmp -s "$source" "$installed"
}

mm_unit_repair_inputs_safe() {
	local source=$1 installed=$2
	[ -f "$source" ] && [ ! -L "$source" ] || return 1
	[ ! -L "$installed" ] || return 1
	[ ! -e "$installed" ] || [ -f "$installed" ]
}

mm_loaded_unit_ready() {
	local source=$1 installed=$2 unit=$3 fragment dropins reload
	mm_reviewed_unit_file_ready "$source" "$installed" || return 1
	fragment=$(systemctl show -p FragmentPath --value "$unit") || return 1
	dropins=$(systemctl show -p DropInPaths --value "$unit") || return 1
	reload=$(systemctl show -p NeedDaemonReload --value "$unit") || return 1
	[ "$fragment" = "$installed" ] || return 1
	[ -z "$dropins" ] || return 1
	[ "$reload" = no ] || return 1
}
