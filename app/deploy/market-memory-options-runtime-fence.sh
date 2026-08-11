#!/usr/bin/env bash
# Runtime receipts for the W1B.5 option-OI isolation boundary. This file is
# sourced by privileged reconcilers and executed read-only as the writer's
# ExecCondition before any credentialed request.
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/macro}
OPTIONS_API_FENCE_MARKER=/run/macro-api-market-memory-options-deny.ready
OPTIONS_RECIPROCAL_FENCE_MARKER=/run/macro-market-memory-options-reciprocal-deny.ready
RECIPROCAL_MARKER_BODY=market-memory-options-reciprocal-deny.v2

mm_runtime_marker_file_ready() {
	local marker=$1 metadata
	[ -f "$marker" ] && [ ! -L "$marker" ] || return 1
	metadata=$(stat -c '%U:%G:%a' "$marker") || return 1
	[ "$metadata" = root:root:644 ]
}

mm_api_fence_marker_ready() {
	local marker_pid marker_invocation extra current_pid current_invocation lines
	mm_runtime_marker_file_ready "$OPTIONS_API_FENCE_MARKER" || return 1
	lines=$(wc -l <"$OPTIONS_API_FENCE_MARKER") || return 1
	[ "$lines" -eq 1 ] || return 1
	read -r marker_pid marker_invocation extra <"$OPTIONS_API_FENCE_MARKER" || return 1
	[ -z "${extra:-}" ] || return 1
	[[ "$marker_pid" =~ ^[1-9][0-9]*$ ]] || return 1
	[[ "$marker_invocation" =~ ^[0-9a-f]{32}$ ]] || return 1
	current_pid=$(systemctl show -p MainPID --value macro-api) || return 1
	current_invocation=$(systemctl show -p InvocationID --value macro-api) || return 1
	[ "$marker_pid" = "$current_pid" ] && \
		[ "$marker_invocation" = "$current_invocation" ]
}

mm_reciprocal_fence_marker_ready() {
	local body lines
	mm_runtime_marker_file_ready "$OPTIONS_RECIPROCAL_FENCE_MARKER" || return 1
	lines=$(wc -l <"$OPTIONS_RECIPROCAL_FENCE_MARKER") || return 1
	[ "$lines" -eq 1 ] || return 1
	IFS= read -r body <"$OPTIONS_RECIPROCAL_FENCE_MARKER" || return 1
	[ "$body" = "$RECIPROCAL_MARKER_BODY" ]
}

mm_write_runtime_marker() {
	local marker=$1 body=$2 temporary
	temporary=$(mktemp /run/.macro-market-memory-options-fence.XXXXXX) || return 1
	printf '%s\n' "$body" >"$temporary" || {
		rm -f "$temporary"
		return 1
	}
	chown root:root "$temporary" || { rm -f "$temporary"; return 1; }
	chmod 0644 "$temporary" || { rm -f "$temporary"; return 1; }
	mv -f "$temporary" "$marker"
}

mm_write_api_fence_marker() {
	local current_pid current_invocation
	current_pid=$(systemctl show -p MainPID --value macro-api) || return 1
	current_invocation=$(systemctl show -p InvocationID --value macro-api) || return 1
	[[ "$current_pid" =~ ^[1-9][0-9]*$ ]] || return 1
	[[ "$current_invocation" =~ ^[0-9a-f]{32}$ ]] || return 1
	mm_write_runtime_marker \
		"$OPTIONS_API_FENCE_MARKER" "$current_pid $current_invocation"
	mm_api_fence_marker_ready
}

mm_write_reciprocal_fence_marker() {
	mm_write_runtime_marker \
		"$OPTIONS_RECIPROCAL_FENCE_MARKER" "$RECIPROCAL_MARKER_BODY"
	mm_reciprocal_fence_marker_ready
}

mm_unit_inactive_without_process() {
	local unit=$1 active_state main_pid control_pid
	active_state=$(systemctl show -p ActiveState --value "$unit") || return 1
	main_pid=$(systemctl show -p MainPID --value "$unit") || return 1
	control_pid=$(systemctl show -p ControlPID --value "$unit") || return 1
	case "$active_state" in
		inactive|failed) ;;
		*) return 1 ;;
	esac
	[ "$main_pid" = 0 ] && [ "$control_pid" = 0 ]
}

mm_options_runtime_boundary_ready() {
	local profile
	mm_api_fence_marker_ready || return 1
	mm_reciprocal_fence_marker_ready || return 1
	mm_loaded_unit_ready \
		"$APP_DIR/app/deploy/macro-api.service" \
		/etc/systemd/system/macro-api.service macro-api.service || return 1
	for profile in source context identity breadth technicals production-records; do
		mm_loaded_unit_ready \
			"$APP_DIR/app/deploy/macro-market-memory-$profile.service" \
			"/etc/systemd/system/macro-market-memory-$profile.service" \
			"macro-market-memory-$profile.service" || return 1
		mm_loaded_unit_ready \
			"$APP_DIR/app/deploy/macro-market-memory-$profile.timer" \
			"/etc/systemd/system/macro-market-memory-$profile.timer" \
			"macro-market-memory-$profile.timer" || return 1
		mm_unit_inactive_without_process \
			"macro-market-memory-$profile.service" || return 1
	done
	mm_loaded_unit_ready \
		"$APP_DIR/app/deploy/macro-market-memory-options.service" \
		/etc/systemd/system/macro-market-memory-options.service \
		macro-market-memory-options.service || return 1
	mm_loaded_unit_ready \
		"$APP_DIR/app/deploy/macro-market-memory-options.timer" \
		/etc/systemd/system/macro-market-memory-options.timer \
		macro-market-memory-options.timer
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
	[ "${1:-}" = --check ] && [ "$#" -eq 1 ] || exit 2
	source "$APP_DIR/app/deploy/market-memory-options-unit-boundary.sh"
	mm_options_runtime_boundary_ready
fi
