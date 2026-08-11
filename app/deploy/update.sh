#!/usr/bin/env bash
# Pull-IF-CHANGED refresh of the served site. Installed as /usr/local/bin/macro-update
# by setup.sh; run by a FREQUENT cron (every few min) + by hand. Cheap no-op when main
# hasn't moved, so it's safe to run often — that's what makes mastermind-x.com track
# main within minutes (the render.yml express lane + the nightly both land here fast)
# instead of waiting on a once-a-night pull.
set -euo pipefail
APP_DIR="/opt/macro"

# Serialize runs. Cron fires every 3 min, but a big nightly render commit can
# take longer than that (fetch + reset + rsync of a multi-hundred-MB site/).
# Without the lock, a second run's `git reset --hard` truncates-and-rewrites
# work-tree files WHILE the first run's rsync is still READING them — and rsync
# then renames a partial/0-byte copy into site.served with a perfectly atomic
# rename. Skipping is free: the next cron tick picks up whatever this run got.
exec 9>/var/lock/macro-update.lock
flock -n 9 || exit 0
source "$APP_DIR/app/deploy/market-memory-options-unit-boundary.sh"
source "$APP_DIR/app/deploy/market-memory-options-runtime-fence.sh"
source "$APP_DIR/app/deploy/market-memory-options-dropin-migration.sh"

OPTIONS_TIMER_WAS_ENABLED=0
if systemctl is-enabled macro-market-memory-options.timer >/dev/null 2>&1; then
	OPTIONS_TIMER_WAS_ENABLED=1
fi
OPTIONS_TIMER_WAS_ACTIVE=0
if systemctl is-active macro-market-memory-options.timer >/dev/null 2>&1; then
	OPTIONS_TIMER_WAS_ACTIVE=1
fi
OPTIONS_TIMER_DISARMED=0
OPTIONS_API_FENCE_MARKER=/run/macro-api-market-memory-options-deny.ready
OPTIONS_RECIPROCAL_FENCE_MARKER=/run/macro-market-memory-options-reciprocal-deny.ready
OPTIONS_RUNTIME_CLOSURE_REGEX='^(app/requirements\.txt|app/deploy/(update\.sh|codex-runtime-setup\.sh|macro-api\.service|macro-market-memory-(options|source|context|identity|breadth|technicals)\.(service|timer)|market-memory-options-(prereqs|unit-boundary|runtime-fence|dropin-migration)\.sh)|scripts/(__init__|capture_market_memory_option_oi)\.py|engine/(__init__\.py|neuralweb/(__init__|market_memory|market_memory_(option_oi_observation|option_oi_store|pit))\.py)|contracts/market_memory/(option_oi_probe_receipt|spy_option_oi_source_observation|option_oi_capture_receipt|option_oi_store)\.v1\.schema\.json|config/market_memory_option_oi_source\.v1\.json|research/licenses/MASSIVE_ENTITLEMENT_RECORD\.md)$'
OPTIONS_RECIPROCAL_CLOSURE_REGEX='^(app/requirements\.txt|app/deploy/(update|market-memory-options-(unit-boundary|runtime-fence|dropin-migration))\.sh|app/deploy/macro-market-memory-(source|context|identity|breadth|technicals)\.(service|timer)|scripts/__init__\.py|engine/(__init__\.py|neuralweb/(__init__|market_memory(_pit)?)\.py))$'
RECIPROCAL_TIMERS_PAUSED=0
OPTIONS_DEFER_REARM_FOR_SELF_UPDATE=0

# BEGIN W1B5_UNIT_STOP_HELPERS
unit_absent_from_manager_and_disk() {
	local unit=$1 installed=$2 load_state
	[ ! -e "$installed" ] && [ ! -L "$installed" ] || return 1
	load_state=$(systemctl show -p LoadState --value "$unit") || return 1
	[ "$load_state" = not-found ]
}

stop_unit_and_verify_inactive() {
	local unit=$1 installed=$2 active_state main_pid control_pid
	if ! systemctl stop "$unit" >/dev/null 2>&1; then
		unit_absent_from_manager_and_disk "$unit" "$installed" || return 1
		return 0
	fi
	active_state=$(systemctl show -p ActiveState --value "$unit") || return 1
	main_pid=$(systemctl show -p MainPID --value "$unit") || return 1
	control_pid=$(systemctl show -p ControlPID --value "$unit") || return 1
	case "$active_state" in
		inactive|failed) ;;
		*) return 1 ;;
	esac
	case "$unit" in
		*.timer)
			# Timers have no execution process. systemd therefore reports these
			# service-only properties as empty on the production release.
			case "$main_pid" in ""|0) ;; *) return 1 ;; esac
			case "$control_pid" in ""|0) ;; *) return 1 ;; esac
			;;
		*.service)
			[ "$main_pid" = 0 ] && [ "$control_pid" = 0 ]
			;;
		*) return 1 ;;
	esac
}
# END W1B5_UNIT_STOP_HELPERS

# BEGIN W1B5_RECIPROCAL_STOP
stop_reciprocal_market_memory_writers() {
	local profile service timer
	rm -f "$OPTIONS_RECIPROCAL_FENCE_MARKER"
	for profile in source context identity breadth technicals; do
		service="macro-market-memory-$profile.service"
		timer="macro-market-memory-$profile.timer"
		if ! stop_unit_and_verify_inactive \
			"$timer" "/etc/systemd/system/$timer"; then
			echo "macro-update: FAILED to pause reciprocal timer $timer" >&2
			return 1
		fi
		if ! stop_unit_and_verify_inactive \
			"$service" "/etc/systemd/system/$service"; then
			echo "macro-update: FAILED to stop reciprocal writer $service" >&2
			return 1
		fi
	done
	RECIPROCAL_TIMERS_PAUSED=1
}
# END W1B5_RECIPROCAL_STOP

reciprocal_market_memory_units_ready() {
	local profile
	for profile in source context identity breadth technicals; do
		mm_loaded_unit_ready \
			"$APP_DIR/app/deploy/macro-market-memory-$profile.service" \
			"/etc/systemd/system/macro-market-memory-$profile.service" \
			"macro-market-memory-$profile.service" || return 1
		mm_loaded_unit_ready \
			"$APP_DIR/app/deploy/macro-market-memory-$profile.timer" \
			"/etc/systemd/system/macro-market-memory-$profile.timer" \
			"macro-market-memory-$profile.timer" || return 1
	done
}

unit_repair_inputs_safe() {
	local source unit
	for source in "$@"; do
		unit=$(basename "$source")
		mm_unit_repair_inputs_safe "$source" "/etc/systemd/system/$unit" || return 1
	done
}

# BEGIN W1B5_TIMER_DISARM
disarm_options_timer() {
	local unit_file_state
	if [ "$OPTIONS_TIMER_DISARMED" -eq 1 ]; then
		return 0
	fi
	if ! systemctl disable --now macro-market-memory-options.timer >/dev/null 2>&1; then
		# Removing the marker is the secondary fail-closed fence: even if an
		# already-loaded timer could not be stopped, its service condition fails.
		rm -f "$OPTIONS_API_FENCE_MARKER"
		if ! unit_absent_from_manager_and_disk \
			macro-market-memory-options.timer \
			/etc/systemd/system/macro-market-memory-options.timer; then
			echo "macro-update: FAILED to disarm option-OI timer" >&2
			return 1
		fi
	fi
	if [ -e /etc/systemd/system/macro-market-memory-options.timer ]; then
		unit_file_state=$(systemctl show -p UnitFileState --value \
			macro-market-memory-options.timer) || return 1
		case "$unit_file_state" in
			disabled|masked) ;;
			*) echo "macro-update: option-OI timer remains enabled" >&2; return 1 ;;
		esac
	fi
	if ! stop_unit_and_verify_inactive \
		macro-market-memory-options.timer \
		/etc/systemd/system/macro-market-memory-options.timer; then
		rm -f "$OPTIONS_API_FENCE_MARKER"
		echo "macro-update: FAILED to stop option-OI timer" >&2
		return 1
	fi
	if ! stop_unit_and_verify_inactive \
		macro-market-memory-options.service \
		/etc/systemd/system/macro-market-memory-options.service; then
		rm -f "$OPTIONS_API_FENCE_MARKER"
		echo "macro-update: FAILED to stop active option-OI writer" >&2
		return 1
	fi
	OPTIONS_TIMER_DISARMED=1
}
# END W1B5_TIMER_DISARM

# ConditionPathExists follows symlinks. Remove any forged/stale marker before
# fetch/reset/runtime mutation so an enabled timer cannot pass the condition in
# the window before the later full boundary reconciliation.
if { [ -e "$OPTIONS_API_FENCE_MARKER" ] || [ -L "$OPTIONS_API_FENCE_MARKER" ]; } && \
   ! mm_api_fence_marker_ready; then
	disarm_options_timer
	rm -f "$OPTIONS_API_FENCE_MARKER" "$OPTIONS_RECIPROCAL_FENCE_MARKER"
fi
if { [ -e "$OPTIONS_RECIPROCAL_FENCE_MARKER" ] || \
     [ -L "$OPTIONS_RECIPROCAL_FENCE_MARKER" ]; } && \
   ! mm_reciprocal_fence_marker_ready; then
	disarm_options_timer
	rm -f "$OPTIONS_API_FENCE_MARKER" "$OPTIONS_RECIPROCAL_FENCE_MARKER"
fi

# A prior tick may have reset the repo and crashed before self-installing this
# updater. In that version-skew state the running predecessor may reconcile but
# must not mint markers or re-arm either boundary; only a later invocation that
# began byte-identical to the reviewed repo updater may do so.
if ! cmp -s "$APP_DIR/app/deploy/update.sh" /usr/local/bin/macro-update; then
	OPTIONS_DEFER_REARM_FOR_SELF_UPDATE=1
	disarm_options_timer
	stop_reciprocal_market_memory_writers
fi

git -C "$APP_DIR" fetch --depth 1 -q origin main
OLD=$(git -C "$APP_DIR" rev-parse HEAD)
NEW=$(git -C "$APP_DIR" rev-parse FETCH_HEAD)
CHANGED=""
REPO_UPDATED=0
RECONCILED=0

if [ "$OLD" != "$NEW" ]; then
	CHANGED=$(git -C "$APP_DIR" diff --name-only "$OLD" "$NEW")
	# BEGIN W1B5_PRE_RESET_GUARD
	# Git rewrites tracked files in place. Stop the credentialed writer before
	# replacing any byte in its exact runtime/source-contract closure.
	if grep -qE "$OPTIONS_RUNTIME_CLOSURE_REGEX" <<<"$CHANGED"; then
		disarm_options_timer
		rm -f "$OPTIONS_API_FENCE_MARKER"
	fi
	if grep -qE '^app/deploy/(update|market-memory-options-(unit-boundary|runtime-fence))\.sh$' \
		<<<"$CHANGED"; then
		# Bash keeps executing the predecessor inode after self-install. It may
		# reconcile, but only the next tick's reviewed inode may re-arm the lane.
		OPTIONS_DEFER_REARM_FOR_SELF_UPDATE=1
	fi
	if grep -qE "$OPTIONS_RECIPROCAL_CLOSURE_REGEX" <<<"$CHANGED"; then
		stop_reciprocal_market_memory_writers
	fi
	# END W1B5_PRE_RESET_GUARD
	git -C "$APP_DIR" reset --hard -q FETCH_HEAD
	REPO_UPDATED=1

	# Publish the served tree ATOMICALLY. `git reset --hard` above rewrites
	# changed files IN PLACE, so Caddy serves a separate rsync target whose
	# per-file temp-write + rename keeps every visible file whole.
	mkdir -p "$APP_DIR/site.served"
	rsync -a --delete --min-size=1 "$APP_DIR/site/" "$APP_DIR/site.served/"

	# Press properties (D14 W1.5) — same atomic-publish contract as site.served,
	# and for the same reason: `git reset --hard` above rewrites changed files IN
	# PLACE, so Caddy must serve a separate rsync target whose per-file temp-write
	# + rename keeps every visible file whole. --min-size=1 refuses to publish a
	# 0-byte file over a good one (the 2026-07-03 white-page incident).
	#
	# The [ -d ] guards are load-bearing, not defensive noise: these trees are
	# built by scripts/build_press_properties.py and may legitimately not exist
	# yet on a box that pulled main before they landed. Without the guard, rsync
	# of a missing source under `set -e` aborts the whole update run — and this
	# script is what keeps the MAIN site tracking main.
	#
	# The Caddy vhosts that serve these roots stay COMMENTED until the cutover
	# (see the marked block in app/deploy/Caddyfile), so syncing them early is
	# free: the files land, nothing serves them, and cutover day is a config flip
	# rather than a first-ever data copy.
	if [ -d "$APP_DIR/properties/news" ]; then
		mkdir -p "$APP_DIR/press_news.served"
		rsync -a --delete --min-size=1 "$APP_DIR/properties/news/" "$APP_DIR/press_news.served/"
	fi
	if [ -d "$APP_DIR/properties/research" ]; then
		mkdir -p "$APP_DIR/press_research.served"
		rsync -a --delete --min-size=1 "$APP_DIR/properties/research/" "$APP_DIR/press_research.served/"
	fi
fi

# Runtime-only company-logo configuration. The committed file is deliberately
# empty; the browser-safe Logo.dev publishable token lives in the root-readable
# VPS env and is materialized only into the served tree after every rsync. The
# server-side secret key is neither required nor accepted here.
LOGO_DEV_TOKEN=""
if [ -r /etc/macro-api.env ]; then
	LOGO_DEV_TOKEN=$(sed -n 's/^LOGO_DEV_PUBLISHABLE_KEY=//p' /etc/macro-api.env | tail -n 1)
fi
case "$LOGO_DEV_TOKEN" in
	pk_*) ;;
	*) LOGO_DEV_TOKEN="" ;;
esac
case "$LOGO_DEV_TOKEN" in
	*[!A-Za-z0-9_-]*) LOGO_DEV_TOKEN="" ;;
esac
mkdir -p "$APP_DIR/site.served"
LOGO_CONFIG_TMP=$(mktemp "$APP_DIR/site.served/.logo_config.XXXXXX")
printf 'window.MMX_LOGO_DEV_TOKEN = window.MMX_LOGO_DEV_TOKEN || "%s";\n' "$LOGO_DEV_TOKEN" > "$LOGO_CONFIG_TMP"
chmod 0644 "$LOGO_CONFIG_TMP"
if ! cmp -s "$LOGO_CONFIG_TMP" "$APP_DIR/site.served/logo_config.js"; then
	mv -f "$LOGO_CONFIG_TMP" "$APP_DIR/site.served/logo_config.js"
else
	rm -f "$LOGO_CONFIG_TMP"
fi

# Do not exit just because Git is current. A prior run may have self-updated
# this script while continuing to execute its old inode, or an operator may
# have drifted an installed unit/config. Reconciliation below is deliberately
# idempotent and must also run on a repository no-op.

# Self-update: setup.sh installs this script ONCE at provisioning; without this
# block a repo-side fix to update.sh only reaches the box when an operator
# re-runs setup.sh by hand. `install` unlinks the destination first, so the
# RUNNING copy (bash holds an fd on the old inode) is untouched — the new
# version simply takes over from the next cron tick. `bash -n` gates a
# syntax-broken file from ever being installed. Runs BEFORE the Caddyfile
# block so a script fix still lands even if a bad Caddyfile aborts the run.
if ! cmp -s "$APP_DIR/app/deploy/update.sh" /usr/local/bin/macro-update; then
	if bash -n "$APP_DIR/app/deploy/update.sh"; then
		install -m 0755 "$APP_DIR/app/deploy/update.sh" /usr/local/bin/macro-update
		RECONCILED=1
		echo "macro-update: self-updated from repo"
	else
		echo "macro-update: refusing self-update — bash -n failed" >&2
	fi
fi

# Caddyfile: reinstall + validate + reload ONLY when it actually changed (a bad
# config can never take the site down — reload is gated on `caddy validate`).
if ! cmp -s "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile; then
	if caddy validate --config "$APP_DIR/app/deploy/Caddyfile" --adapter caddyfile; then
		install -m 0644 "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile
		systemctl reload caddy 2>/dev/null || systemctl restart caddy
		RECONCILED=1
	else
		echo "macro-update: refusing Caddyfile update — validation failed" >&2
	fi
fi

# Codex CLI: keep the provider runtime pinned and self-healing just like the
# reviewed systemd units below. Authentication is durable VPS state under the
# root-only /var/lib/macro-codex* stores and is never copied into git.
if ! bash "$APP_DIR/app/deploy/codex-runtime-setup.sh" --quiet; then
	echo "macro-update: Codex runtime reconciliation failed; Claude/DeepSeek fallbacks remain available" >&2
fi

# macro-api systemd sandbox: keep the installed unit aligned with the reviewed
# repo copy. Validate before installation; a broken unit never replaces the
# running one. The restart decision below includes this path.
# Provision the serving root and the disjoint private writer root before unit
# validation/restart.  Both units use non-optional path mounts, so an absent
# path fails closed instead of widening either side of the trust boundary.
install -d -m 0700 /var/lib/macro-market-memory
install -d -m 0700 /var/lib/macro-market-memory/public
install -d -m 0700 /var/lib/macro-market-memory/public/trusted-v1
install -d -m 0700 /var/lib/macro-market-memory/state
install -d -m 0700 /var/lib/macro-market-memory/state/sources
install -d -m 0700 /var/lib/macro-market-memory/state/context-projection
install -d -m 0700 /var/lib/macro-market-memory/state/identity-v1
install -d -m 0700 /var/lib/macro-market-memory/state/breadth-v1
install -d -m 0700 /var/lib/macro-market-memory/state/technicals-v1
# Unit verification needs the static account and empty deny anchors.  The
# service-writable profile and credential file are provisioned only after
# macro-api proves a new deny namespace.
OPTIONS_RECONCILIATION_COMPLETE=0
# BEGIN W1B5_TIMER_EXIT_GUARD
options_fail_closed_on_exit() {
	local status=$?
	trap - EXIT
	if [ "$OPTIONS_RECONCILIATION_COMPLETE" -ne 1 ]; then
		disarm_options_timer || status=1
		if [ "$status" -eq 0 ]; then
			status=1
		fi
	fi
	exit "$status"
}
trap options_fail_closed_on_exit EXIT
# END W1B5_TIMER_EXIT_GUARD

# W1A has no scheduled context writer, so directory provisioning alone cannot
# create its manifest/genesis/HEAD. Reconcile and authenticate that metadata on
# every tick before API unit validation or restart. Any unsafe partial, tampered,
# symlinked, or unwritable store aborts readiness; no capture is fabricated.
if ! /opt/macro-api/.venv/bin/python "$APP_DIR/scripts/initialize_market_memory_w1a.py" \
	--repository-root "$APP_DIR" \
	--store /var/lib/macro-market-memory/public; then
	echo "macro-update: W1A public generation initialization failed; refusing API readiness" >&2
	exit 1
fi

# A healthy no-op updater must not cancel and recreate the nonpersistent daily
# timer.  Validate first; disarm only when identity/anchor repair is required.
if ! bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" \
	--check-identity-only >/dev/null 2>&1; then
	disarm_options_timer
	bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" --identity-only
fi
OPTIONS_CREDENTIAL_READY=0
API_UNIT_UPDATED=0
API_UNIT_READY=0

if ! mm_reviewed_unit_file_ready \
	"$APP_DIR/app/deploy/macro-api.service" \
	/etc/systemd/system/macro-api.service; then
	disarm_options_timer
	rm -f "$OPTIONS_API_FENCE_MARKER"
	mm_unit_repair_inputs_safe \
		"$APP_DIR/app/deploy/macro-api.service" \
		/etc/systemd/system/macro-api.service || {
		echo "macro-update: refusing unsafe macro-api unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "$APP_DIR/app/deploy/macro-api.service"; then
		install -m 0644 "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service
		systemctl daemon-reload
		API_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: macro-api systemd sandbox updated"
	else
		echo "macro-update: refusing macro-api unit update — systemd-analyze verify failed" >&2
	fi
fi
# Production historically supplied the optional Ollama endpoint through one
# hand-installed drop-in. Migrate only after the exact reviewed macro-api
# fragment containing that same EnvironmentFile line is installed. Unknown
# overrides or a failed canonical install leave the working legacy file intact.
if [ -e "$MM_LEGACY_API_DROPIN_DIR" ] || [ -L "$MM_LEGACY_API_DROPIN_DIR" ]; then
	disarm_options_timer
	stop_reciprocal_market_memory_writers
	rm -f "$OPTIONS_API_FENCE_MARKER"
	if ! mm_remove_exact_legacy_api_ollama_dropin \
		"$APP_DIR/app/deploy/macro-api.service" \
		/etc/systemd/system/macro-api.service; then
		echo "macro-update: refusing unsafe legacy macro-api drop-in migration" >&2
		exit 1
	fi
	systemctl daemon-reload
	RECONCILED=1
	echo "macro-update: migrated reviewed legacy macro-api Ollama drop-in"
fi
if mm_reviewed_unit_file_ready \
	"$APP_DIR/app/deploy/macro-api.service" \
	/etc/systemd/system/macro-api.service && \
   ! mm_loaded_unit_ready \
	"$APP_DIR/app/deploy/macro-api.service" \
	/etc/systemd/system/macro-api.service macro-api.service; then
	disarm_options_timer
	rm -f "$OPTIONS_API_FENCE_MARKER"
	systemctl daemon-reload
fi
if mm_loaded_unit_ready \
	"$APP_DIR/app/deploy/macro-api.service" \
	/etc/systemd/system/macro-api.service macro-api.service; then
	API_UNIT_READY=1
else
	disarm_options_timer
	rm -f "$OPTIONS_API_FENCE_MARKER"
	echo "macro-update: macro-api effective unit boundary is not reviewed/current" >&2
fi

# A /run receipt proves that all five pre-existing Market Memory writers were
# stopped at least once after boot/unit drift and any later starts used the
# exact reviewed, drop-in-free unit fragments. Its absence pauses the writers
# before their legacy reconciliation blocks can install, enable, or start them.
RECIPROCAL_UNITS_READY=0
if reciprocal_market_memory_units_ready; then
	RECIPROCAL_UNITS_READY=1
fi
if ! mm_reciprocal_fence_marker_ready || \
   [ "$RECIPROCAL_UNITS_READY" -ne 1 ]; then
	disarm_options_timer
	stop_reciprocal_market_memory_writers
	# Refresh manager state only after every potentially old-namespace writer
	# is confirmed inactive. Persistent drop-ins remain visible and fail the
	# later exact attestation; this reload repairs only ordinary stale fragments.
	systemctl daemon-reload
fi

# Serving dependencies: reconcile against a content stamp on every cron pass,
# not only the first pull that changed requirements.txt. A transient PyPI error
# therefore retries next tick, and the API never restarts into code whose declared
# dependencies failed to install. api-setup.sh writes the same stamp on provision.
API_DEPS_UPDATED=0
API_DEPS_OK=1
API_REQ_STAMP=/opt/macro-api/.requirements.sha256
API_REQ_HASH=$(sha256sum "$APP_DIR/app/requirements.txt" | cut -d' ' -f1)
API_INSTALLED_REQ_HASH=$(cat "$API_REQ_STAMP" 2>/dev/null || true)
if [ "$API_REQ_HASH" != "$API_INSTALLED_REQ_HASH" ]; then
	# The option writer shares this interpreter. Never let its scheduled
	# oneshot overlap a partially-mutated environment.
	disarm_options_timer
	stop_reciprocal_market_memory_writers
	rm -f "$OPTIONS_API_FENCE_MARKER"
	if [ -x /opt/macro-api/.venv/bin/pip ] \
		&& /opt/macro-api/.venv/bin/pip install -q -r "$APP_DIR/app/requirements.txt"; then
		API_REQ_TMP=$(mktemp /opt/macro-api/.requirements.XXXXXX)
		printf '%s\n' "$API_REQ_HASH" > "$API_REQ_TMP"
		chmod 0644 "$API_REQ_TMP"
		mv -f "$API_REQ_TMP" "$API_REQ_STAMP"
		API_DEPS_UPDATED=1
		RECONCILED=1
		echo "macro-update: macro-api dependencies reconciled"
	else
		API_DEPS_OK=0
		echo "macro-update: macro-api dependency reconciliation FAILED; keeping the running API" >&2
	fi
fi

# W1B.0 trusted-source writer: credential-free, network-dark, and private. It
# is safe to install and arm automatically because its only input is the exact
# committed CPIAUCSL collector artifact and its only writable path is the
# root-only source store above. The engine intake validates the hardened
# manifest, exact bytes, and append-only generation before advancing HEAD.
MARKET_MEMORY_SOURCE_UNIT_UPDATED=0
MARKET_MEMORY_SOURCE_UNIT_SOURCES=(
	"$APP_DIR/app/deploy/macro-market-memory-source.service"
	"$APP_DIR/app/deploy/macro-market-memory-source.timer"
)
if ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_SOURCE_UNIT_SOURCES[0]}" /etc/systemd/system/macro-market-memory-source.service || \
   ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_SOURCE_UNIT_SOURCES[1]}" /etc/systemd/system/macro-market-memory-source.timer; then
	unit_repair_inputs_safe "${MARKET_MEMORY_SOURCE_UNIT_SOURCES[@]}" || {
		echo "macro-update: refusing unsafe source unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "${MARKET_MEMORY_SOURCE_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${MARKET_MEMORY_SOURCE_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! mm_reviewed_unit_file_ready "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				[ ! -L "/etc/systemd/system/$UNIT" ] || {
					echo "macro-update: refusing symlinked unit $UNIT" >&2
					exit 1
				}
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				MARKET_MEMORY_SOURCE_UNIT_UPDATED=1
			fi
		done
		if [ "$MARKET_MEMORY_SOURCE_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
				systemctl restart macro-market-memory-source.timer 2>/dev/null || true
			fi
			RECONCILED=1
			echo "macro-update: Market Memory trusted-source units updated"
		fi
	else
		echo "macro-update: refusing Market Memory source unit update — systemd-analyze verify failed" >&2
	fi
fi
if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
	systemctl enable --now macro-market-memory-source.timer >/dev/null 2>&1 || \
		echo "macro-update: macro-market-memory-source.timer could not be enabled" >&2
fi

# Run immediately when the reviewed writer, engine contract, or exact CPI bytes
# advance. A failure is visible in journald and retryable by the hourly timer;
# it must not interrupt site/API deployment or fall back to an older artifact.
MARKET_MEMORY_SOURCE_RUN_NEEDED=0
if [ "$MARKET_MEMORY_SOURCE_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(scripts/ingest_market_memory_sources\.py|engine/neuralweb/market_memory_sources\.py|contracts/market_memory/.*source.*\.schema\.json|data/fred_vintage/release_targets/(manifest\.json|CPIAUCSL_all_vintages\.parquet))$'; then
	MARKET_MEMORY_SOURCE_RUN_NEEDED=1
fi
if [ "$MARKET_MEMORY_SOURCE_RUN_NEEDED" -eq 1 ]; then
	if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 1 ]; then
		echo "macro-update: deferring Market Memory source intake until reciprocal boundary attestation" >&2
	elif [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: deferring Market Memory source intake — shared runtime dependencies are not current" >&2
	elif ! systemctl start macro-market-memory-source.service; then
		echo "macro-update: Market Memory source intake failed closed; hourly timer will retry" >&2
	fi
fi

# W1B.1 trusted context publisher: network-dark and credential-free. It writes
# exact raw evidence only below the API-inaccessible state tree and advances the
# separate public trusted-v1 HEAD only after that evidence and the typed feature
# object are durable.
MARKET_MEMORY_CONTEXT_UNIT_UPDATED=0
MARKET_MEMORY_CONTEXT_UNIT_SOURCES=(
	"$APP_DIR/app/deploy/macro-market-memory-context.service"
	"$APP_DIR/app/deploy/macro-market-memory-context.timer"
)
if ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_CONTEXT_UNIT_SOURCES[0]}" /etc/systemd/system/macro-market-memory-context.service || \
   ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_CONTEXT_UNIT_SOURCES[1]}" /etc/systemd/system/macro-market-memory-context.timer; then
	unit_repair_inputs_safe "${MARKET_MEMORY_CONTEXT_UNIT_SOURCES[@]}" || {
		echo "macro-update: refusing unsafe context unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "${MARKET_MEMORY_CONTEXT_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${MARKET_MEMORY_CONTEXT_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! mm_reviewed_unit_file_ready "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				[ ! -L "/etc/systemd/system/$UNIT" ] || {
					echo "macro-update: refusing symlinked unit $UNIT" >&2
					exit 1
				}
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				MARKET_MEMORY_CONTEXT_UNIT_UPDATED=1
			fi
		done
		if [ "$MARKET_MEMORY_CONTEXT_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
				systemctl restart macro-market-memory-context.timer 2>/dev/null || true
			fi
			RECONCILED=1
			echo "macro-update: Market Memory trusted-context units updated"
		fi
	else
		echo "macro-update: refusing Market Memory context unit update — systemd-analyze verify failed" >&2
	fi
fi
if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
	systemctl enable --now macro-market-memory-context.timer >/dev/null 2>&1 || \
		echo "macro-update: macro-market-memory-context.timer could not be enabled" >&2
fi

MARKET_MEMORY_CONTEXT_RUN_NEEDED=0
if [ "$MARKET_MEMORY_CONTEXT_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(scripts/project_market_memory_context\.py|engine/neuralweb/market_memory(_pit|_identity|_projection|_trusted)?\.py|contracts/market_memory/(macro_regime_snapshot|macro_regime_feature_object|trusted_capture_receipt)\.v1\.schema\.json|config/market_memory_canary\.v1\.json|engine/run\.py|data/regime/latest\.json)$'; then
	MARKET_MEMORY_CONTEXT_RUN_NEEDED=1
fi
if [ "$MARKET_MEMORY_CONTEXT_RUN_NEEDED" -eq 1 ]; then
	if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 1 ]; then
		echo "macro-update: deferring Market Memory context projection until reciprocal boundary attestation" >&2
	elif [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: deferring Market Memory context projection — shared runtime dependencies are not current" >&2
	elif ! systemctl start macro-market-memory-context.service; then
		echo "macro-update: Market Memory context projection failed closed; hourly timer will retry" >&2
	fi
fi

# W1B.2 private identity-observation publisher: network-dark, credential-free,
# and deliberately disconnected from the API-readable trusted-v1 store. It
# records legacy roster snapshots only as reconstruction and can admit a future
# observation operationally only when the collector's receipt-last contract
# authenticates the exact snapshot bytes.
MARKET_MEMORY_IDENTITY_UNIT_UPDATED=0
MARKET_MEMORY_IDENTITY_UNIT_SOURCES=(
	"$APP_DIR/app/deploy/macro-market-memory-identity.service"
	"$APP_DIR/app/deploy/macro-market-memory-identity.timer"
)
if ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_IDENTITY_UNIT_SOURCES[0]}" /etc/systemd/system/macro-market-memory-identity.service || \
   ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_IDENTITY_UNIT_SOURCES[1]}" /etc/systemd/system/macro-market-memory-identity.timer; then
	unit_repair_inputs_safe "${MARKET_MEMORY_IDENTITY_UNIT_SOURCES[@]}" || {
		echo "macro-update: refusing unsafe identity unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "${MARKET_MEMORY_IDENTITY_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${MARKET_MEMORY_IDENTITY_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! mm_reviewed_unit_file_ready "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				[ ! -L "/etc/systemd/system/$UNIT" ] || {
					echo "macro-update: refusing symlinked unit $UNIT" >&2
					exit 1
				}
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				MARKET_MEMORY_IDENTITY_UNIT_UPDATED=1
			fi
		done
		if [ "$MARKET_MEMORY_IDENTITY_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
				systemctl restart macro-market-memory-identity.timer 2>/dev/null || true
			fi
			RECONCILED=1
			echo "macro-update: Market Memory identity-observation units updated"
		fi
	else
		echo "macro-update: refusing Market Memory identity unit update — systemd-analyze verify failed" >&2
	fi
fi
if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
	systemctl enable --now macro-market-memory-identity.timer >/dev/null 2>&1 || \
		echo "macro-update: macro-market-memory-identity.timer could not be enabled" >&2
fi

MARKET_MEMORY_IDENTITY_RUN_NEEDED=0
if [ "$MARKET_MEMORY_IDENTITY_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(scripts/ingest_market_memory_identity\.py|engine/neuralweb/market_memory_identity_(observation|store)\.py|lib/symbol_directory_receipts\.py|collectors/symbol_directory\.py|contracts/(market_memory/(spy_listing_(object|observation)|identity_observation_(prepared|capture_receipt|store_receipts))\.v1\.schema\.json|symbol_directory/symbol_directory_completion_receipt\.v1\.schema\.json)|data/symbol_directory/(snapshots|cik_map|receipts)/.*)$'; then
	MARKET_MEMORY_IDENTITY_RUN_NEEDED=1
fi
if [ "$MARKET_MEMORY_IDENTITY_RUN_NEEDED" -eq 1 ]; then
	if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 1 ]; then
		echo "macro-update: deferring Market Memory identity accrual until reciprocal boundary attestation" >&2
	elif [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: deferring Market Memory identity accrual — shared runtime dependencies are not current" >&2
	elif ! systemctl start macro-market-memory-identity.service; then
		echo "macro-update: Market Memory identity accrual failed closed; hourly timer will retry" >&2
	fi
fi

# W1B.3B private SPY raw-close technical actual-output publisher. The only
# network access is the fixed public R2 manifest/object transaction embedded in
# reviewed code; it has no credentials and remains disconnected from the API,
# trusted-v1, Prophet, options, outcomes, ranking, sizing, and execution.
MARKET_MEMORY_TECHNICALS_UNIT_UPDATED=0
MARKET_MEMORY_TECHNICALS_UNIT_SOURCES=(
	"$APP_DIR/app/deploy/macro-market-memory-technicals.service"
	"$APP_DIR/app/deploy/macro-market-memory-technicals.timer"
)
if ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_TECHNICALS_UNIT_SOURCES[0]}" /etc/systemd/system/macro-market-memory-technicals.service || \
   ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_TECHNICALS_UNIT_SOURCES[1]}" /etc/systemd/system/macro-market-memory-technicals.timer; then
	unit_repair_inputs_safe "${MARKET_MEMORY_TECHNICALS_UNIT_SOURCES[@]}" || {
		echo "macro-update: refusing unsafe technicals unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "${MARKET_MEMORY_TECHNICALS_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${MARKET_MEMORY_TECHNICALS_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! mm_reviewed_unit_file_ready "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				[ ! -L "/etc/systemd/system/$UNIT" ] || {
					echo "macro-update: refusing symlinked unit $UNIT" >&2
					exit 1
				}
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				MARKET_MEMORY_TECHNICALS_UNIT_UPDATED=1
			fi
		done
		if [ "$MARKET_MEMORY_TECHNICALS_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
				systemctl restart macro-market-memory-technicals.timer 2>/dev/null || true
			fi
			RECONCILED=1
			echo "macro-update: Market Memory technical actual-output units updated"
		fi
	else
		echo "macro-update: refusing Market Memory technical unit update — systemd-analyze verify failed" >&2
	fi
fi
if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
	systemctl enable --now macro-market-memory-technicals.timer >/dev/null 2>&1 || \
		echo "macro-update: macro-market-memory-technicals.timer could not be enabled" >&2
fi

MARKET_MEMORY_TECHNICALS_RUN_NEEDED=0
if [ "$MARKET_MEMORY_TECHNICALS_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(scripts/capture_market_memory_technicals\.py|engine/neuralweb/market_memory_technical_(observation|store)\.py|contracts/market_memory/(spy_daily_price_source_observation|spy_raw_close_ratio_snapshot|technicals_actual_output_capture_receipt|technicals_actual_output_store)\.v1\.schema\.json|config/market_memory_(canary|technical_price_basis)\.v1\.json|lib/nyse_calendar\.py|research/licenses/MASSIVE_ENTITLEMENT_RECORD\.md)$'; then
	MARKET_MEMORY_TECHNICALS_RUN_NEEDED=1
fi
if [ "$MARKET_MEMORY_TECHNICALS_RUN_NEEDED" -eq 1 ]; then
	if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 1 ]; then
		echo "macro-update: deferring Market Memory technical capture until reciprocal boundary attestation" >&2
	elif [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: deferring Market Memory technical capture — shared runtime dependencies are not current" >&2
	elif ! systemctl start macro-market-memory-technicals.service; then
		echo "macro-update: Market Memory technical capture failed closed; hourly timer will retry" >&2
	fi
fi

# W1B.3A private breadth actual-output publisher: network-dark,
# credential-free, and deliberately disconnected from both trusted-v1 and the
# API. It captures only the exact current Git-owned tip after frozen calendar,
# identity, constituent, and freshness checks; historical rows are never
# upgraded by this lane.
MARKET_MEMORY_BREADTH_UNIT_UPDATED=0
MARKET_MEMORY_BREADTH_UNIT_SOURCES=(
	"$APP_DIR/app/deploy/macro-market-memory-breadth.service"
	"$APP_DIR/app/deploy/macro-market-memory-breadth.timer"
)
if ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_BREADTH_UNIT_SOURCES[0]}" /etc/systemd/system/macro-market-memory-breadth.service || \
   ! mm_reviewed_unit_file_ready "${MARKET_MEMORY_BREADTH_UNIT_SOURCES[1]}" /etc/systemd/system/macro-market-memory-breadth.timer; then
	unit_repair_inputs_safe "${MARKET_MEMORY_BREADTH_UNIT_SOURCES[@]}" || {
		echo "macro-update: refusing unsafe breadth unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "${MARKET_MEMORY_BREADTH_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${MARKET_MEMORY_BREADTH_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! mm_reviewed_unit_file_ready "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				[ ! -L "/etc/systemd/system/$UNIT" ] || {
					echo "macro-update: refusing symlinked unit $UNIT" >&2
					exit 1
				}
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				MARKET_MEMORY_BREADTH_UNIT_UPDATED=1
			fi
		done
		if [ "$MARKET_MEMORY_BREADTH_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
				systemctl restart macro-market-memory-breadth.timer 2>/dev/null || true
			fi
			RECONCILED=1
			echo "macro-update: Market Memory breadth actual-output units updated"
		fi
	else
		echo "macro-update: refusing Market Memory breadth unit update — systemd-analyze verify failed" >&2
	fi
fi
if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 0 ]; then
	systemctl enable --now macro-market-memory-breadth.timer >/dev/null 2>&1 || \
		echo "macro-update: macro-market-memory-breadth.timer could not be enabled" >&2
fi

MARKET_MEMORY_BREADTH_RUN_NEEDED=0
if [ "$MARKET_MEMORY_BREADTH_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(scripts/capture_market_memory_breadth\.py|engine/neuralweb/market_memory_(actual_output_store|breadth_observation)\.py|contracts/market_memory/breadth_(source_observation|factors_snapshot|actual_output_capture_receipt|actual_output_store)\.v1\.schema\.json|data/breadth/(breadth|constituents)\.parquet|config/market_memory_canary\.v1\.json|lib/nyse_calendar\.py)$'; then
	MARKET_MEMORY_BREADTH_RUN_NEEDED=1
fi
if [ "$MARKET_MEMORY_BREADTH_RUN_NEEDED" -eq 1 ]; then
	if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 1 ]; then
		echo "macro-update: deferring Market Memory breadth capture until reciprocal boundary attestation" >&2
	elif [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: deferring Market Memory breadth capture — shared runtime dependencies are not current" >&2
	elif ! systemctl start macro-market-memory-breadth.service; then
		echo "macro-update: Market Memory breadth capture failed closed; hourly timer will retry" >&2
	fi
fi

# W1B.5 private, future-only option-OI endpoint availability canary. It makes
# exactly one bounded first-page request with a systemd credential, follows no
# pagination, and never constructs a chain, identity, OI state, GEX, replay
# input, or trading feature. The separate service identity and store root keep
# credentialed response evidence outside every existing Market Memory writer
# and the API namespace.
MARKET_MEMORY_OPTIONS_UNIT_UPDATED=0
OPTIONS_UNITS_READY=0
MARKET_MEMORY_OPTIONS_UNIT_SOURCES=(
	"$APP_DIR/app/deploy/macro-market-memory-options.service"
	"$APP_DIR/app/deploy/macro-market-memory-options.timer"
)
if ! mm_reviewed_unit_file_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[0]}" \
	/etc/systemd/system/macro-market-memory-options.service || \
   ! mm_reviewed_unit_file_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[1]}" \
	/etc/systemd/system/macro-market-memory-options.timer; then
	disarm_options_timer
	unit_repair_inputs_safe "${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[@]}" || {
		echo "macro-update: refusing unsafe option-OI unit repair input" >&2
		exit 1
	}
	if systemd-analyze verify "${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! mm_reviewed_unit_file_ready "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				MARKET_MEMORY_OPTIONS_UNIT_UPDATED=1
			fi
		done
		if [ "$MARKET_MEMORY_OPTIONS_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			RECONCILED=1
			echo "macro-update: Market Memory option-OI canary units updated"
		fi
	else
		echo "macro-update: refusing option-OI unit update — systemd-analyze verify failed" >&2
	fi
fi
if mm_reviewed_unit_file_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[0]}" \
	/etc/systemd/system/macro-market-memory-options.service && \
   mm_reviewed_unit_file_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[1]}" \
	/etc/systemd/system/macro-market-memory-options.timer && \
   { ! mm_loaded_unit_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[0]}" \
	/etc/systemd/system/macro-market-memory-options.service \
	macro-market-memory-options.service || \
     ! mm_loaded_unit_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[1]}" \
	/etc/systemd/system/macro-market-memory-options.timer \
	macro-market-memory-options.timer; }; then
	disarm_options_timer
	systemctl daemon-reload
fi
if mm_loaded_unit_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[0]}" \
	/etc/systemd/system/macro-market-memory-options.service \
	macro-market-memory-options.service && \
   mm_loaded_unit_ready \
	"${MARKET_MEMORY_OPTIONS_UNIT_SOURCES[1]}" \
	/etc/systemd/system/macro-market-memory-options.timer \
	macro-market-memory-options.timer; then
	OPTIONS_UNITS_READY=1
else
	disarm_options_timer
	echo "macro-update: option-OI effective units are not reviewed/current" >&2
fi

MARKET_MEMORY_OPTIONS_RUN_NEEDED=0
if [ "$OPTIONS_UNITS_READY" -eq 1 ] && { \
	[ "$MARKET_MEMORY_OPTIONS_UNIT_UPDATED" -eq 1 ] || \
	grep -qE "$OPTIONS_RUNTIME_CLOSURE_REGEX" <<<"$CHANGED" || \
	[ "$OPTIONS_TIMER_WAS_ENABLED" -eq 0 ]; \
}; then
	MARKET_MEMORY_OPTIONS_RUN_NEEDED=1
fi

# macro-api: restart ONLY when its own code changed (avoid blipping /api on every
# site/ render commit). "Its own code" = every Python module import-cached by the
# running uvicorn, because sys.modules pins the OLD module object for the life of
# the process: without a restart the new file sits on disk while the API keeps
# serving the previous code — live in git, dead in production, with no signal.
#
# INCLUSION RULE (keep the list narrow but complete). A path belongs here when the
# API process imports it, either:
#   (a) at load     — app/*.py and their module-level engine/lib closure; or
#   (b) at request  — a function-level import on a path an API endpoint reaches
#                     (cached after the first call, same trap, just later).
# Every module below was confirmed against the import graph of app/*.py, not
# guessed. When adding a lazy `from engine...` / `from lib...` import to any app/
# router or to a module already listed here, extend this list in the same commit —
# tests/test_deploy_update_self_heal.py recomputes the load-time closure and fails
# CI if it drifts out of this regex.
#
# Why each group is here:
#   app/.*\.py             every router is import-cached (the old list omitted
#                          regwall.py/paywall.py: code could deploy while the
#                          running API kept the previous access policy)
#   neuralweb/*            /api/ask + /api/brain: ask_brain → cortex, llm_auth,
#                          envelope → synapse, tushare_freshness; brain_gateway →
#                          chart_perception, doctrine, key_pool (CMX W2/W4)
#   earnings evidence      brain_gateway lazily reaches earnings_context_reader,
#                          whose exact-evidence validator imports the named
#                          earnings_narrative contract closure and PRESS adapter.
#                          All become request-time cached after the first read.
#   codex_provider/runner  llm_auth's request-time Codex fallback imports both;
#                          either module stays cached after the first Codex turn
#   research_vault/        app/research.py imports catalog, corpus, download_quota,
#                          view_ratelimit, watermark (→ sidecar, r2_store) at MODULE
#                          level. Whole-package pattern on purpose: this is the
#                          vault's serving layer, so a new module added here is
#                          API-cached too and must not need a second fix. Omitting
#                          it silently froze download caps / anti-scrape limits —
#                          #3654 escaped only because it also touched app/research.py.
#   fundamental_forensics/ app/forensics.py imports private_state through the
#                          package, whose __init__ loads the pure kernel modules;
#                          all are therefore pinned in macro-api sys.modules.
#   capital_structure/*    app/capital_structure.py imports projection at module
#                          load; projection and its package __init__ pull the
#                          event spine, normalized document-term kernel, and
#                          source-identity helpers into sys.modules. All stay
#                          pinned until macro-api restarts. Named narrowly so
#                          nightly-only compilers do not blip the serving plane.
#   government_revenue/*   app/government_revenue.py imports workspace through
#                          the non-inert package __init__, which loads the award,
#                          dossier, exact entity-resolution, federation,
#                          freshness, metric, opportunity, PIT, budget-program,
#                          IDV-dossier, and subaward-dossier helpers.
#                          These serving-plane modules remain cached for the
#                          life of macro-api and must advance with a deploy.
#                          Their lru_cache'd validators pin the referenced
#                          contracts/government_revenue schemas in-process for
#                          the same lifetime, so those schema files are named
#                          in the trigger too; schema reads with no cache (the
#                          budget graph, the coverage builders) re-read per
#                          call, self-heal without a restart, and stay out.
#                          tests/test_deploy_update_self_heal.py derives the
#                          pinned set from the app/ import closure.
#   company_intelligence/* app/company_intelligence.py imports the verified
#                          reader's public artifact contract.  Importing this
#                          package executes its non-inert __init__, which loads
#                          contracts, health, and views; all are pinned in the
#                          API process for the lifetime of the public ticker
#                          context route.
#   seasonality/           app/seasonality.py's single `from engine.seasonality
#                          import screener` executes the package __init__, which
#                          eagerly re-exports contracts, event_clock, model,
#                          multiplicity, prophet_bridge, regime, screener and
#                          universe. All nine were confirmed against a live
#                          interpreter's sys.modules, not read off import lines.
#                          Named, not globbed, and the seven exclusions are
#                          load-bearing: calendar, calibration, event_study,
#                          foundation, panel, scanner and state are the
#                          numpy/pandas research modules that __init__ keeps out
#                          on purpose (calibration and event_study resolve
#                          through its PEP 562 __getattr__ only when something
#                          asks, and no app/ path asks). Globbing would blip /api
#                          on every research commit in an actively-built program.
#   context_index/         brain_gateway → packet.build_packet, which top-level
#                          imports fusion/gitinfo/lexical/structured. Named, not
#                          globbed: ingest/chunking/health/schema/sources are
#                          nightly-only builders the API never imports.
#   marketing/             brain_gateway's chart path → chart_render (load_ohlcv,
#                          render_chart_v2) + confluence_source. The other twelve
#                          are NOT optional and NOT reached by reading import
#                          lines: importing ANY engine.marketing submodule first
#                          executes the PACKAGE __init__, which imports state →
#                          authority, charter, claims, cmo, departments, economics,
#                          events, ledgers, opportunity_bus, publication. All
#                          fourteen were confirmed against a live interpreter's
#                          sys.modules, not inferred. Named, not globbed: 34 of the
#                          48 marketing modules are nightly-only, and outbox/
#                          rejections are admin-only (see the admin list below).
#   engine/live_quotes.py  app/tape.py REST quote fetch (→ lib/config.py)
#   lib/*                  ai_costs + mastermind_response_log log every chat call;
#                          config.py is a module-level dep of live_quotes
#
# Deliberately NOT here (do not "fix" these — they would blip /api for nothing):
#   - Doctrine CONTENT (engine/neuralweb/doctrine/*.md AND analyst/*.md): both
#     libraries reload the .md files on mtime change, so prose-only edits go
#     live with no restart.
#   - Data/artifact files read from disk per request.
#   - The nightly-only closure behind cortex.run() (constitution → qledger →
#     ai_desk → master_brain → china_*): the API imports cortex for its tool
#     schemas/implementations only and never calls run(), so those ~90 modules are
#     NOT in the API's sys.modules. Adding them would restart /api on nearly every
#     engine commit — exactly what this narrow list exists to prevent.
API_RESTART_CONFIRMED=0
API_RESTART_NEEDED=0
# BEGIN MACRO_API_RESTART_TRIGGER
if [ "$API_UNIT_UPDATED" -eq 1 ] || ! mm_api_fence_marker_ready || grep -qE '^(app/.*\.py|app/requirements\.txt|app/deploy/macro-api\.service|config/site_access\.yml|engine/neuralweb/(ask_brain|cortex|brain_gateway|chart_perception|chat_plain_words|company_intelligence_reader|earnings_context_reader|doctrine|analyst_doctrine|market_packet|market_memory|market_memory_pit|market_memory_playback|market_memory_projection|market_memory_trusted|brain_market_intel|brain_analogues|brain_curve|brain_user_memory|envelope|key_pool|synapse)\.py|engine/earnings_narrative/(__init__|context_packets|contracts|digest|private_publication|promotion|public_wire|story|story_packets)\.py|engine/press/(__init__|earnings_adapter)\.py|engine/(codex_provider|llm_auth|options_issue_desk|portfolio_brief|live_quotes|tushare_freshness)\.py|engine/codex_lane/runner\.py|engine/research_vault/.*\.py|engine/fundamental_forensics/.*\.py|engine/biocatalyst/.*\.py|engine/sector_intelligence/.*\.py|engine/company_intelligence/.*\.py|engine/seasonality/(__init__|contracts|event_clock|model|multiplicity|program_watch|prophet_bridge|regime|screener|universe)\.py|engine/capital_structure/(__init__|document_terms|event_spine|projection|source_identity)\.py|engine/government_revenue/(__init__|amount_semantics|award_events|budget_program|candidates|dossiers|entity_resolution|federation|freshness|idv_bridge|idv_dossiers|metrics|opportunities|point_in_time|subaward_dossiers|workspace)\.py|contracts/government_revenue/(government_entity_coverage\.v1|government_idv_bridge\.v1|government_idv_dossiers\.v1|government_procurement_(event|workspace)\.v2|government_recipient_resolution_coverage\.v1|government_revenue_candidate(_queue|_historical_suppressions|_issuance_corrections)?\.v1|government_revenue_dossiers\.v1|government_subaward_dossiers\.v1)\.schema\.json|contracts/options/options\.(issue_desk(_proposal|_decision)?|issue_receipt)\.v1\.schema\.json|engine/context_index/(packet|fusion|gitinfo|lexical|structured)\.py|engine/marketing/(__init__|authority|chart_render|charter|claims|cmo|confluence_source|departments|economics|events|ledgers|opportunity_bus|publication|state)\.py|lib/(config|ai_costs|mastermind_response_log|nyse_calendar|user_prefs|tiers)\.py)$' <<<"$CHANGED" || \
   [ "$API_DEPS_UPDATED" -eq 1 ]; then
	API_RESTART_NEEDED=1

fi
# END MACRO_API_RESTART_TRIGGER
if [ "$API_RESTART_NEEDED" -eq 1 ]; then
	disarm_options_timer
	rm -f "$OPTIONS_API_FENCE_MARKER"
	# Verified restart, not fire-and-forget: on 2026-07-30 the old one-liner
	# (`... && systemctl restart macro-api || true`) left the API on its 5-hour-old
	# PID after a matching deploy, and the `|| true` destroyed every trace of why.
	# Log the PID transition, and retry once when the restart failed or the PID
	# provably did not change — all output lands in macro-update.log.
	if [ "$API_UNIT_READY" -ne 1 ]; then
		echo "macro-update: macro-api restart skipped because the reviewed unit is not installed exactly" >&2
	elif [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: macro-api restart skipped because dependency reconciliation failed" >&2
	elif systemctl is-enabled macro-api >/dev/null 2>&1; then
		systemctl daemon-reload
		API_NEED_DAEMON_RELOAD=$(systemctl show -p NeedDaemonReload --value macro-api)
		[ "$API_NEED_DAEMON_RELOAD" = no ] || {
			echo "macro-update: macro-api manager state remains stale after daemon-reload" >&2
			exit 1
		}
		PRE_PID="$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')"
		API_RESTART_RC=0
		systemctl restart macro-api || API_RESTART_RC=$?
		POST_PID="$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')"
		if [ "$API_RESTART_RC" -eq 0 ] && [[ "$POST_PID" =~ ^[1-9][0-9]*$ ]] && [ "$POST_PID" != "$PRE_PID" ]; then
			API_RESTART_CONFIRMED=1
			echo "macro-api restarted pid $PRE_PID -> $POST_PID"
		else
			echo "macro-api restart ANOMALY rc=$API_RESTART_RC pid $PRE_PID -> $POST_PID; retrying once"
			sleep 2
			API_RETRY_RC=0
			systemctl restart macro-api || API_RETRY_RC=$?
			FINAL_PID="$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')"
			if [ "$API_RETRY_RC" -eq 0 ] && [[ "$FINAL_PID" =~ ^[1-9][0-9]*$ ]] && [ "$FINAL_PID" != "$PRE_PID" ]; then
				API_RESTART_CONFIRMED=1
				echo "macro-api restart retry succeeded pid $PRE_PID -> $FINAL_PID"
			else
				echo "macro-api restart RETRY FAILED rc=$API_RETRY_RC pid $PRE_PID -> $FINAL_PID" >&2
			fi
		fi
	fi
fi

# The marker attests a verified PID transition into the installed unit that
# hides both the disjoint raw store and its dedicated credential source.  It is
# removed whenever that unit changes and /run clears it on reboot, so option
# evidence cannot exist while an older API namespace remains able to read it.
if [ "$API_RESTART_CONFIRMED" -eq 1 ] && [ "$API_UNIT_READY" -eq 1 ] && \
   [ "$(systemctl show -p NeedDaemonReload --value macro-api)" = no ] && \
   cmp -s "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service && \
   grep -Fxq 'InaccessiblePaths=/var/lib/macro-market-memory-options' /etc/systemd/system/macro-api.service && \
   grep -Fxq 'InaccessiblePaths=/etc/macro-market-memory-options' /etc/systemd/system/macro-api.service; then
	mm_write_api_fence_marker
fi

OPTIONS_API_FENCE_READY=0
if mm_api_fence_marker_ready && \
   [ "$API_UNIT_READY" -eq 1 ] && \
   [ "$(systemctl show -p NeedDaemonReload --value macro-api)" = no ] && \
   cmp -s "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service && \
   grep -Fxq 'InaccessiblePaths=/var/lib/macro-market-memory-options' /etc/systemd/system/macro-api.service && \
   grep -Fxq 'InaccessiblePaths=/etc/macro-market-memory-options' /etc/systemd/system/macro-api.service; then
	OPTIONS_API_FENCE_READY=1
else
	rm -f "$OPTIONS_API_FENCE_MARKER"
fi

RECIPROCAL_UNITS_READY=0
if reciprocal_market_memory_units_ready; then
	RECIPROCAL_UNITS_READY=1
fi
if [ "$RECIPROCAL_UNITS_READY" -ne 1 ]; then
	disarm_options_timer
	stop_reciprocal_market_memory_writers
	echo "macro-update: reciprocal Market Memory units are not reviewed/current" >&2
fi

if [ "$OPTIONS_API_FENCE_READY" -eq 1 ] && \
   [ "$RECIPROCAL_UNITS_READY" -eq 1 ] && \
   [ "$OPTIONS_UNITS_READY" -eq 1 ]; then
	OPTIONS_STATUS=0
	bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" \
		--check-ready >/dev/null 2>&1 || OPTIONS_STATUS=$?
	if [ "$OPTIONS_STATUS" -eq 0 ]; then
		OPTIONS_CREDENTIAL_READY=1
	else
		disarm_options_timer
		if bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh"; then
			OPTIONS_CREDENTIAL_READY=1
		else
			OPTIONS_STATUS=$?
			if [ "$OPTIONS_STATUS" -ne 2 ]; then
				echo "macro-update: option-OI private-root provisioning failed" >&2
				exit "$OPTIONS_STATUS"
			fi
			echo "macro-update: option-OI credential absent; lane remains disarmed" >&2
		fi
	fi
else
	echo "macro-update: option-OI private state not provisioned before API fence" >&2
fi

# Publish the reciprocal receipt only after the exact loaded units have been
# re-attested. If this tick paused them, no old-namespace process is alive; any
# later timer/service start therefore inherits the reviewed reciprocal denies.
if [ "$RECIPROCAL_UNITS_READY" -eq 1 ] && \
   [ "$OPTIONS_DEFER_REARM_FOR_SELF_UPDATE" -eq 0 ]; then
	mm_write_reciprocal_fence_marker
else
	rm -f "$OPTIONS_RECIPROCAL_FENCE_MARKER"
fi

OPTIONS_BOUNDARY_READY=0
if [ "$OPTIONS_CREDENTIAL_READY" -eq 1 ] && [ "$OPTIONS_UNITS_READY" -eq 1 ] && \
   [ "$OPTIONS_API_FENCE_READY" -eq 1 ] && [ "$RECIPROCAL_UNITS_READY" -eq 1 ] && \
   mm_reciprocal_fence_marker_ready && \
   [ "$OPTIONS_DEFER_REARM_FOR_SELF_UPDATE" -eq 0 ]; then
	OPTIONS_BOUNDARY_READY=1
fi

# BEGIN W1B5_TIMER_FINALIZATION
if [ "$OPTIONS_BOUNDARY_READY" -eq 1 ]; then
	# A deploy-triggered smoke capture happens once and before timer arming.  A
	# failed first capture is retried only by the weekday timer, never every
	# three-minute updater tick.
	if [ "$MARKET_MEMORY_OPTIONS_RUN_NEEDED" -eq 1 ]; then
		if [ "$API_DEPS_OK" -ne 1 ]; then
			echo "macro-update: deferring option-OI canary — shared runtime dependencies are not current" >&2
		elif ! systemctl start macro-market-memory-options.service; then
			echo "macro-update: option-OI capture failed closed; weekday timer will retry" >&2
		fi
	fi
	if [ "$OPTIONS_TIMER_WAS_ENABLED" -eq 0 ] || \
	   [ "$OPTIONS_TIMER_WAS_ACTIVE" -eq 0 ] || \
	   [ "$OPTIONS_TIMER_DISARMED" -eq 1 ]; then
		# The historical latch no longer describes current state once an enable
		# attempt begins.  Reset it so a partial enable failure is forcibly undone.
		OPTIONS_TIMER_DISARMED=0
		if ! systemctl enable --now macro-market-memory-options.timer >/dev/null 2>&1 || \
		   ! systemctl is-enabled macro-market-memory-options.timer >/dev/null 2>&1 || \
		   ! systemctl is-active macro-market-memory-options.timer >/dev/null 2>&1; then
			disarm_options_timer
			echo "macro-update: macro-market-memory-options.timer could not be enabled" >&2
		fi
	fi
else
	disarm_options_timer
	echo "macro-update: option-OI lane remains disarmed until units, credential, and API fence are verified" >&2
fi
if [ "$RECIPROCAL_TIMERS_PAUSED" -eq 1 ] && \
   [ "$RECIPROCAL_UNITS_READY" -eq 1 ] && \
   [ "$OPTIONS_DEFER_REARM_FOR_SELF_UPDATE" -eq 0 ]; then
	for RECIPROCAL_PROFILE in source context identity breadth technicals; do
		systemctl start "macro-market-memory-$RECIPROCAL_PROFILE.timer"
	done
fi
OPTIONS_RECONCILIATION_COMPLETE=1
trap - EXIT
# END W1B5_TIMER_FINALIZATION

# Live-plane systemd definitions are installed by live-setup.sh. Once that setup
# has happened, keep unit/resource/timer changes tracking main automatically.
# Python task code needs no restart because every lane is a fresh oneshot process.
if systemctl is-enabled macro-live-fast.timer >/dev/null 2>&1 && \
   echo "$CHANGED" | grep -qE '^app/deploy/macro-live-(fast|snapshot|bars)\.(service|timer)$'; then
	LIVE_UNIT_SOURCES=()
	for UNIT in \
		macro-live-fast.service macro-live-fast.timer \
		macro-live-snapshot.service macro-live-snapshot.timer \
		macro-live-bars.service macro-live-bars.timer
	do
		LIVE_UNIT_SOURCES+=("$APP_DIR/app/deploy/$UNIT")
	done
	if systemd-analyze verify "${LIVE_UNIT_SOURCES[@]}"; then
		for UNIT_SOURCE in "${LIVE_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
		done
		systemctl daemon-reload
		systemctl restart macro-live-fast.timer macro-live-snapshot.timer macro-live-bars.timer
	else
		echo "macro-update: refusing live-plane unit update — systemd-analyze verify failed" >&2
	fi
fi

# PROPHET LIVE evaluator lane (research/PROPHET_LIVE_INTRADAY_SIGNALS_MASTERPLAN_BY_FABLE.md
# §4.2a). Its own block, not a fourth entry in the list above, for two reasons: the
# three lanes there are ONE orchestrator invoked with three --lane arguments, and
# widening that regex would restart all three timers whenever this unrelated unit
# changed. Same narrow allow-list discipline — exactly the two paths this lane owns.
#
# Unlike the block above it also arms itself, because go-live for this program is a
# REPO COMMIT and nothing else: the unit did not exist when live-setup.sh was last run
# on the box, so a CHANGED-only trigger would install a timer that nobody ever enables.
# `enable --now` on an already-enabled, already-active timer is a systemd no-op, and
# the absent-file clause makes the block self-healing when an earlier tick's
# systemd-analyze failed or an operator removed the unit (macro-update installing it
# twice must be, and is, a no-op).
#
# The live plane must already exist (macro-live-fast.timer enabled): this lane reads
# what those lanes publish, so on any host without them it would have nothing to read.
# That guard is also what keeps this block inert on a box that is not the VPS.
#
# The .service is NEVER restarted. It is a oneshot — `systemctl restart` would RUN a
# pass out of band, off the ET-windowed schedule, with the R2 debounce predecessor
# from whenever the last legitimate tick was. Only the timer is (re)armed.
if systemctl is-enabled macro-live-fast.timer >/dev/null 2>&1 && \
   { echo "$CHANGED" | grep -qE '^app/deploy/macro-live-prophet\.(service|timer)$' || \
     [ ! -f /etc/systemd/system/macro-live-prophet.timer ]; }; then
	PROPHET_UNIT_SOURCES=(
		"$APP_DIR/app/deploy/macro-live-prophet.service"
		"$APP_DIR/app/deploy/macro-live-prophet.timer"
	)
	if systemd-analyze verify "${PROPHET_UNIT_SOURCES[@]}"; then
		PROPHET_UNIT_UPDATED=0
		for UNIT_SOURCE in "${PROPHET_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! cmp -s "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				PROPHET_UNIT_UPDATED=1
			fi
		done
		if [ "$PROPHET_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			systemctl restart macro-live-prophet.timer 2>/dev/null || true
			RECONCILED=1
			echo "macro-update: macro-live-prophet units updated"
		fi
		systemctl enable --now macro-live-prophet.timer >/dev/null 2>&1 || \
			echo "macro-update: macro-live-prophet.timer could not be enabled" >&2
	else
		echo "macro-update: refusing macro-live-prophet unit update — systemd-analyze verify failed" >&2
	fi
fi

# CLOSE-PASS MIRROR lane (W-L1a). Its own block for the same reason the Prophet
# block is separate: a widened regex would restart unrelated timers whenever this
# unit changed. Same self-arming contract — go-live for this lane is a REPO COMMIT
# and nothing else, so a CHANGED-only trigger would install a timer nobody ever
# enables, and the absent-file clause self-heals a failed verify or an operator
# removal. The live-fast guard marks the serving VPS and keeps the block inert
# everywhere else.
#
# The .service is NEVER restarted — it is a oneshot, and `systemctl restart` would
# RUN a mirror pass out of band. Only the timer is (re)armed.
if systemctl is-enabled macro-live-fast.timer >/dev/null 2>&1 && \
   { echo "$CHANGED" | grep -qE '^app/deploy/macro-live-closepass\.(service|timer)$' || \
     [ ! -f /etc/systemd/system/macro-live-closepass.timer ]; }; then
	CLOSEPASS_UNIT_SOURCES=(
		"$APP_DIR/app/deploy/macro-live-closepass.service"
		"$APP_DIR/app/deploy/macro-live-closepass.timer"
	)
	if systemd-analyze verify "${CLOSEPASS_UNIT_SOURCES[@]}"; then
		CLOSEPASS_UNIT_UPDATED=0
		for UNIT_SOURCE in "${CLOSEPASS_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! cmp -s "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				CLOSEPASS_UNIT_UPDATED=1
			fi
		done
		if [ "$CLOSEPASS_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			systemctl restart macro-live-closepass.timer 2>/dev/null || true
			RECONCILED=1
			echo "macro-update: macro-live-closepass units updated"
		fi
		systemctl enable --now macro-live-closepass.timer >/dev/null 2>&1 || \
			echo "macro-update: macro-live-closepass.timer could not be enabled" >&2
	else
		echo "macro-update: refusing macro-live-closepass unit update — systemd-analyze verify failed" >&2
	fi
fi

# FRESHNESS SENTINEL — the dead-man switch that must live OUTSIDE GitHub
# (masterplan W1). Same self-arming contract as the Prophet block above and for
# the same reason: go-live is a REPO COMMIT — the unit did not exist when
# live-setup.sh last ran, so a CHANGED-only trigger would install a timer nobody
# ever enables. The live-fast guard marks the serving VPS (the box this watch
# must run on) and keeps the block inert everywhere else. `enable --now` on an
# already-enabled timer is a systemd no-op; the absent-file clause self-heals an
# earlier failed verify or an operator removal.
#
# The .service is NEVER restarted — it is a oneshot; only the timer is (re)armed.
if systemctl is-enabled macro-live-fast.timer >/dev/null 2>&1 && \
   { echo "$CHANGED" | grep -qE '^app/deploy/macro-sentinel\.(service|timer)$' || \
     [ ! -f /etc/systemd/system/macro-sentinel.timer ]; }; then
	SENTINEL_UNIT_SOURCES=(
		"$APP_DIR/app/deploy/macro-sentinel.service"
		"$APP_DIR/app/deploy/macro-sentinel.timer"
	)
	if systemd-analyze verify "${SENTINEL_UNIT_SOURCES[@]}"; then
		SENTINEL_UNIT_UPDATED=0
		for UNIT_SOURCE in "${SENTINEL_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! cmp -s "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				SENTINEL_UNIT_UPDATED=1
			fi
		done
		if [ "$SENTINEL_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			systemctl restart macro-sentinel.timer 2>/dev/null || true
			RECONCILED=1
			echo "macro-update: macro-sentinel units updated"
		fi
		systemctl enable --now macro-sentinel.timer >/dev/null 2>&1 || \
			echo "macro-update: macro-sentinel.timer could not be enabled" >&2
	else
		echo "macro-update: refusing macro-sentinel unit update — systemd-analyze verify failed" >&2
	fi
fi

# PRESS-FEEDS is a long-running daemon, unlike the oneshot live-plane timers
# above. Arming remains an explicit operator choice: this block neither installs
# an absent unit nor enables/starts an inactive one. Once the operator has
# installed it, however, the reviewed unit must track main and an ACTIVE daemon
# must restart when import-cached code changes; otherwise a merged press-lane fix
# lands on disk while the old Python process runs forever.
PRESS_UNIT_UPDATED=0
if [ -f /etc/systemd/system/marketing-press-feeds.service ] && \
   ! cmp -s "$APP_DIR/app/deploy/marketing-press-feeds.service" /etc/systemd/system/marketing-press-feeds.service; then
	if systemd-analyze verify "$APP_DIR/app/deploy/marketing-press-feeds.service"; then
		install -m 0644 "$APP_DIR/app/deploy/marketing-press-feeds.service" /etc/systemd/system/marketing-press-feeds.service
		systemctl daemon-reload
		PRESS_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: marketing-press-feeds systemd sandbox updated"
	else
		echo "macro-update: refusing marketing-press-feeds unit update — systemd-analyze verify failed" >&2
	fi
fi

# BioCatalyst B1 is a separate source-canonical lane.  A routine production
# pull must never install, enable, or start it: doing so could turn a partially
# configured evidence collector live.  Reconcile only a fully operator-installed
# worker pair and dedicated runtime. The root-only retention heartbeat units are
# copied beside that pair but remain dormant unless separately armed. Dependencies are built in a versioned
# staging virtualenv and verified before one atomic current-symlink swap. No
# live runtime is ever pip-mutated, and a failed candidate leaves the previous
# runtime and timer arming state untouched.
BIOCATALYST_UNITS_INSTALLED=0
if [ -f /etc/systemd/system/macro-biocatalyst.service ] && \
   [ -f /etc/systemd/system/macro-biocatalyst.timer ]; then
	BIOCATALYST_UNITS_INSTALLED=1
fi

BIOCATALYST_RUNTIME_UPDATED=0
BIOCATALYST_RUNTIME_READY=0
if [ "$BIOCATALYST_UNITS_INSTALLED" -eq 1 ] && \
   [ -d /opt/macro-biocatalyst ] && \
   { [ -L /opt/macro-biocatalyst/current ] || \
     [ -x /opt/macro-biocatalyst/.venv/bin/python ]; } && \
   [ -f "$APP_DIR/app/deploy/biocatalyst-requirements.txt" ] && \
   [ -f "$APP_DIR/app/deploy/biocatalyst-runtime.sh" ]; then
	BIOCATALYST_REQUIREMENTS_HASH="$(sha256sum "$APP_DIR/app/deploy/biocatalyst-requirements.txt" | awk '{print $1}')"
	BIOCATALYST_INSTALLED_HASH=""
	if bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --verify; then
		BIOCATALYST_INSTALLED_HASH="$(awk 'NR == 1 { print $1 }' /opt/macro-biocatalyst/current/.requirements.sha256)"
		if [ "$BIOCATALYST_REQUIREMENTS_HASH" = "$BIOCATALYST_INSTALLED_HASH" ]; then
			BIOCATALYST_RUNTIME_READY=1
		fi
	fi
	if [ "$BIOCATALYST_RUNTIME_READY" -ne 1 ]; then
		if bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --install \
			"$APP_DIR/app/deploy/biocatalyst-requirements.txt"; then
			BIOCATALYST_RUNTIME_READY=1
			BIOCATALYST_RUNTIME_UPDATED=1
			RECONCILED=1
			echo "macro-update: BioCatalyst isolated runtime atomically reconciled without changing arming state"
		else
			echo "macro-update: BioCatalyst staged runtime failed; previous runtime remains selected" >&2
		fi
	fi
fi

# Reconcile unit files only after the runtime referenced by the reviewed service
# has passed verification. Preserve both timers' operator-controlled arming state.
BIOCATALYST_UNIT_UPDATED=0
if [ "$BIOCATALYST_UNITS_INSTALLED" -eq 1 ] && \
   { ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.service" /etc/systemd/system/macro-biocatalyst.service || \
     ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.timer" /etc/systemd/system/macro-biocatalyst.timer || \
     ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.service || \
     ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer; }; then
	# Capture arming before copying a new unit. In particular, a newly introduced
	# heartbeat timer must remain absent/disabled after reconciliation rather than
	# becoming an accidental activation path merely because its source now exists.
	BIOCATALYST_TIMER_WAS_ENABLED=0
	BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED=0
	if [ -f /etc/systemd/system/macro-biocatalyst.timer ] && \
		systemctl is-enabled --quiet macro-biocatalyst.timer; then
		BIOCATALYST_TIMER_WAS_ENABLED=1
	fi
	if [ -f /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer ] && \
		systemctl is-enabled --quiet macro-biocatalyst-activation-heartbeat.timer; then
		BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED=1
	fi
	if [ "$BIOCATALYST_RUNTIME_READY" -ne 1 ]; then
		echo "macro-update: refusing BioCatalyst unit update — verified dedicated runtime unavailable" >&2
	elif systemd-analyze verify "$APP_DIR/app/deploy/macro-biocatalyst.service" \
		"$APP_DIR/app/deploy/macro-biocatalyst.timer" \
		"$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" \
		"$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer"; then
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.service" /etc/systemd/system/macro-biocatalyst.service; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst.service" /etc/systemd/system/macro-biocatalyst.service
		fi
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.timer" /etc/systemd/system/macro-biocatalyst.timer; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst.timer" /etc/systemd/system/macro-biocatalyst.timer
		fi
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.service; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.service
		fi
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer
		fi
		systemctl daemon-reload
		BIOCATALYST_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: BioCatalyst systemd lane updated without changing its arming state"
		if [ "$BIOCATALYST_TIMER_WAS_ENABLED" -eq 1 ]; then
			systemctl restart macro-biocatalyst.timer
		fi
		if [ "$BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED" -eq 1 ]; then
			systemctl restart macro-biocatalyst-activation-heartbeat.timer
		fi
	else
		echo "macro-update: refusing BioCatalyst unit update — systemd-analyze verify failed" >&2
	fi
fi

# The daemon imports these modules into one persistent interpreter. Config YAML
# is deliberately absent: it is re-read on every 75-second tick and needs no
# restart. Keep the engine/marketing pattern broad because every submodule import
# executes that package's non-inert __init__ first, and the press pipeline reaches
# multiple modules lazily according to the source/item path.
if [ "$PRESS_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(app/deploy/marketing-press-feeds\.service|scripts/marketing_fastlane_daemon\.py|engine/news_translate\.py|engine/marketing/.*\.py|engine/(codex_provider|llm_auth)\.py|engine/codex_lane/runner\.py|lib/(ai_costs|config)\.py)$'; then
	if systemctl is-active --quiet marketing-press-feeds; then
		systemctl restart marketing-press-feeds
	fi
fi

# admin console: restart ONLY when its own code changed, so the deployed panel at
# admin.mastermind-x.com tracks main automatically (config/secrets live in the
# untouched /etc/macro-admin.env, so a restart never loses them). "Its own code"
# includes the engine/lib modules the panels lazily import — cached in sys.modules
# after the first request, so without a restart an engine-side fix (e.g. a
# key_pool.py change to the Raw Key Usage join) never reaches the running panel;
# data files are read from disk per request and need no restart.
#
# INCLUSION RULE — the same one the macro-api list above uses. admin/ is ALL panel
# code, so a function-level import there is import-cached exactly like a
# module-level one, just from the first request that reaches it; both kinds seed
# this list. Each seed is then expanded through MODULE-LEVEL imports only, because
# those are what actually execute on load. A nightly-only tail hanging off a DEEP
# function-level import is not cached and stays out (see the exclusions below).
# Three seed forms count, and grepping for `from engine`/`from lib` finds only the
# first: static imports, `importlib.import_module("engine...")` string literals
# (ai_cost, orchestrator_chat, neural_web all use this form), and the PACKAGE
# __init__ that Python executes before any submodule. Keep this list in sync when
# adding any of them — tests/test_deploy_update_self_heal.py recomputes the closure
# and fails CI if it drifts.
#
# Why each group is here:
#   admin/*                every panel module is import-cached by the process
#   lib/*                  ai_cost + orchestrator_chat → ai_costs;
#                          mastermind_logs → mastermind_response_log
#   neuralweb/*            metabolism_panel + orchestrator_chat → key_pool;
#                          orchestrator_chat → ask_brain; neural_web →
#                          support_map, orchestrator_log
#   metabolism/*           metabolism_panel → throttle; server manual-run gate →
#                          budget_gate
#   engine/{codex_provider,llm_auth,prophet_integrity}.py + engine/codex_lane/runner.py
#                          orchestrator_chat Codex fallback + prophet.py
#                          deliberation-spend panel; marketing.py → copywriter imports
#                          the canonical Prophet correction projection at load time
#   marketing/             marketing.py's outbox approve/reject/decide endpoints →
#                          outbox + rejections. marketing.py's Ad Central panel →
#                          ad_central → ad_allocator, ad_arena, ad_stats. The other
#                          twelve ride the package __init__ (→ state → authority,
#                          charter, claims, cmo, departments, economics, events,
#                          ledgers, opportunity_bus, publication) — confirmed
#                          against a live interpreter's sys.modules. Named, not
#                          globbed: 30 of the 53 marketing modules are nightly-only.
#                          (ad_creative/ad_matrix are NOT here: the panel reads the
#                          creatives ledger, it does not build creatives.)
#   marketing/sentinel     marketing.py's ramp resolver (resolve_ramp) + the
#                          /api/marketing/sentinel panel endpoints — the ramp
#                          caps would deploy dead to the running panel without
#                          a restart (2026-07-28, same class as the outbox gap).
#   scripts/               marketing.py's publish dry-run → marketing_publisher
#                          → copywriter (top-level import: the post-time language
#                          gate banned_language() must fail loudly, so the publisher
#                          imports it at module scope — which puts copywriter in
#                          the panel's load-time closure too).
#   marketing/social_publisher
#                          Same edge, one module further (2026-08-08): the
#                          publisher imports subscription_locked/lock_expires_at
#                          at module scope for the same "must fail loudly" reason
#                          — a lazily-imported lock predicate that failed to
#                          import would read as "no lock", i.e. silently restore
#                          the requeue loop it exists to stop. That top-level
#                          import is what puts social_publisher in the panel's
#                          closure, so it belongs here rather than in the
#                          nightly-only list below.
#   sentinel               marketing.py's caps_by_account (#3884) → resolve_ramp:
#                          the per-account D08 ramp caps shown in the outbox +
#                          publisher payloads import sentinel into the panel.
#
# Deliberately NOT here (they would blip the panel for nothing):
#   - site/ and data/ artifacts, read from disk per request.
#   - engine/neuralweb/cortex.py and the nightly lane behind it. The panel's only
#     entry into ask_brain is _post_filter_advice() (the advice guard); the
#     tool-schema/dispatch paths that lazily import cortex are never called from
#     admin, so cortex is absent from the panel's sys.modules. admin ships its own
#     tool dispatcher.
#   - The rest of engine/marketing (breaking_feed, seo_director, …) —
#     nightly-only, never imported by a panel. social_publisher WAS listed here
#     and no longer is: see its entry above. A name in this list is a claim about
#     the closure, so it has to be deleted the moment the closure disagrees.
# Admin systemd sandbox: reconcile the reviewed unit before deciding whether to
# restart, so a unit-only hardening/provider change cannot land dead on disk.
ADMIN_UNIT_UPDATED=0
if ! cmp -s "$APP_DIR/admin/deploy/admin.service" /etc/systemd/system/admin.service; then
	if systemd-analyze verify "$APP_DIR/admin/deploy/admin.service"; then
		install -m 0644 "$APP_DIR/admin/deploy/admin.service" /etc/systemd/system/admin.service
		systemctl daemon-reload
		ADMIN_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: admin systemd sandbox updated"
	else
		echo "macro-update: refusing admin unit update — systemd-analyze verify failed" >&2
	fi
fi

# XG-W6 added four that ARE panel imports: labels + learned_rules (the Learning
# panel), health_monitor + blind_identity (the Desk Health panel). Without them
# here, a deploy that changed a halt threshold would leave the admin serving the
# old module out of sys.modules — and the panel that reports whether a desk is
# halted is the last one that should be stale.
#
# XG-W8 adds engine/press/{__init__,desk_planner}.py. The Press panel's cadence
# block now reports the RESOLVED cap (0 while the W2R desk-note lane is dark),
# and it gets that number by calling the planner's own `_triage_cap` rather than
# re-deriving the stricter-of rule — a panel that computes its own answer is a
# panel that can disagree with the engine. That call puts both modules in the
# admin's load-time closure, so without them here a deploy that changed the cap
# resolver would leave the panel serving the old rule out of sys.modules: the
# exact class the outbox gap (2026-07-26) and the four XG-W6 panel modules fixed.
# Only these two — research_triage/research_veto/research_lane are reached solely
# through desk_planner's function-level imports on the PLANNING path, which the
# panel never calls.
#
# The Intelligence Desk approve endpoint adds engine/marketing/{story_lock,
# wire_routing}.py. That endpoint is the ONE admin path that emits a post, and
# both modules are gates on it: wire_routing decides which desk owns the emission
# and story_lock enforces one-owner-per-conversation across desks. Left out here,
# a deploy that retuned the routing table or widened the lock window would leave
# the panel queueing against the OLD rule out of sys.modules — the outbox gap
# (2026-07-26) again, but on the path where being stale means a wrong-desk or
# double-owner post rather than a stale reading.
if [ "$ADMIN_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(admin/.*|lib/(ai_costs|mastermind_response_log|tiers)\.py|engine/(codex_provider|llm_auth|macro_thesis|prophet_integrity)\.py|engine/codex_lane/runner\.py|engine/neuralweb/(key_pool|ask_brain|support_map|orchestrator_log|trade_memory)\.py|engine/metabolism/(throttle|budget_gate)\.py|engine/marketing/(__init__|accounts|ad_allocator|ad_arena|ad_central|ad_stats|approval_desk|authority|cadence_resolver|charter|claims|cmo|cold_read|copywriter|departments|economics|events|ledgers|market_clock|media_publish|opportunity_bus|outbox|personas|publication|rejections|blind_identity|health_monitor|labels|learned_rules|reply_critics|reply_discovery|reply_drafter|reply_export|reply_producer|reply_queue|reply_voice|rewrite|sentinel|social_publisher|state|story_lock|wire_routing)\.py|engine/press/(__init__|desk_planner)\.py|scripts/marketing_publisher\.py)$'; then
	systemctl is-enabled admin >/dev/null 2>&1 && systemctl restart admin || true
fi

if [ "$REPO_UPDATED" -eq 1 ] || [ "$RECONCILED" -eq 1 ]; then
	echo "macro-update $(date -u +%FT%TZ) ${OLD:0:8}..$(git -C "$APP_DIR" rev-parse --short HEAD)"
fi
