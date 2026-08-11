#!/usr/bin/env bash
# Provision the isolated B1S2b BioCatalyst fixed-cohort transport lane.
#
# This script installs a dedicated service identity, a root-owned membership
# configuration root, private state, and two systemd units.  It NEVER enables or
# starts the unit or the timer, never writes a credential, never writes cohort
# membership, and never touches the B0a worker lane's paths.  Installing this
# lane therefore causes no collector traffic and opens no outcome-family clock:
# per research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md a clock opens only once
# collection is proven, through an activation receipt.
set -euo pipefail

APP_DIR=/opt/macro
SERVICE_SOURCE="$APP_DIR/app/deploy/biocatalyst-fixed-cohort.service"
TIMER_SOURCE="$APP_DIR/app/deploy/biocatalyst-fixed-cohort.timer"
SERVICE_DEST=/etc/systemd/system/macro-biocatalyst-fixed-cohort.service
TIMER_DEST=/etc/systemd/system/macro-biocatalyst-fixed-cohort.timer
SERVICE_UNIT=macro-biocatalyst-fixed-cohort.service
TIMER_UNIT=macro-biocatalyst-fixed-cohort.timer

ENV_FILE=/etc/macro-biocatalyst-fixed-cohort.env
CONFIG_ROOT=/etc/macro-biocatalyst-fixed-cohort
MANIFEST_ROOT="$CONFIG_ROOT/manifests"
ACTIVE_POINTER="$CONFIG_ROOT/active.json"

STATE_ROOT=/var/lib/macro-biocatalyst-fixed-cohort
RUN_ROOT="$STATE_ROOT/runs"
RECEIPT_ROOT="$STATE_ROOT/receipts"
OPERATIONAL_ROOT="$STATE_ROOT/operational"

SERVICE_USER=macro-biocatalyst-fixed-cohort
SERVICE_GROUP=macro-biocatalyst-fixed-cohort
RUNTIME_ROOT=/opt/macro-biocatalyst-fixed-cohort
RUNTIME_CURRENT="$RUNTIME_ROOT/current"

# The B0a worker lane. This installer must never read, write, or reconcile it.
B0A_STATE_ROOT=/var/lib/macro-biocatalyst
B0A_ENV_FILE=/etc/macro-biocatalyst.env
B0A_CONTROL_ENV_FILE=/etc/macro-biocatalyst-control.env

log() {
	echo "biocatalyst-fixed-cohort-setup: $*"
}

die() {
	log "$*" >&2
	exit 1
}

usage() {
	cat <<'USAGE'
Usage: biocatalyst-fixed-cohort-setup.sh [--install|--verify-prereqs|--reconcile|--mask|--unmask-note]

  --install         provision identity, roots, and units.  Never enables or starts anything.
  --verify-prereqs  check ownership, modes, env-file shape, and unit syntax only.
  --reconcile       refresh unit FILES only when both units are already installed,
                    preserving their operator-controlled arming state.
  --mask            systemd-mask both units so nothing can start them by accident.
  --unmask-note     print the operator instruction to unmask; this script never unmasks.

The root-owned /etc/macro-biocatalyst-fixed-cohort.env file (root:root, mode 0600)
carries TRANSPORT ENABLEMENT AND LIMITS ONLY:
  BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED=0   # 0 keeps the lane dark; only "1" enables I/O
  BIOCATALYST_FIXED_COHORT_USER_AGENT=<descriptive contact string>

It may NEVER carry cohort membership.  Membership lives exclusively in the
root-owned immutable manifests under
/etc/macro-biocatalyst-fixed-cohort/manifests/{cohort_id}.{content_sha256}.json
with /etc/macro-biocatalyst-fixed-cohort/active.json holding an exact byte copy
of the selected manifest.  active.json is a regular file, never a symlink, and is
rotated only through the runtime CLI's --mode rotate/rollback path, which records
an immutable BC-O1a receipt before the pointer moves.

This lane holds no R2 credentials and cannot write the public projection.
USAGE
}

# Membership may never be smuggled through the environment file. These mirror
# MEMBERSHIP_ENV_SEGMENTS / MEMBERSHIP_ENV_PHRASES in
# engine/biocatalyst/fixed_cohort_runtime.py, so a mistake is caught at
# provisioning rather than at 03:00 on an armed host. Segments are matched as
# whole underscore-delimited words: a raw substring rule would flag unrelated
# names such as AWS_LAMBDA_FUNCTION_NAME, and a fence that fires on innocent
# names is a fence that gets deleted.
forbidden_env_segments=(
	ALLOWLIST
	MEMBER
	MEMBERS
	MEMBERSHIP
	NCT
	NCTID
	NCTIDS
	NCTS
)
forbidden_env_phrases=(
	COHORT_ID
	COHORT_IDS
	COHORT_LIST
	COHORT_MEMBER
	COHORT_NCT
	MANIFEST_JSON
	NCT_ID
	NCT_IDS
	QUERY_ID
	STUDY_ID
	STUDY_IDS
)

assert_no_membership_in_env_file() {
	local segment phrase
	[ -f "$ENV_FILE" ] || return 0
	for segment in "${forbidden_env_segments[@]}"; do
		if grep -Eq "^([A-Z0-9]+_)*${segment}(_[A-Z0-9]+)*=" "$ENV_FILE"; then
			die "$ENV_FILE must not carry cohort membership (matched segment ${segment})"
		fi
	done
	for phrase in "${forbidden_env_phrases[@]}"; do
		if grep -Eq "^[A-Z0-9_]*${phrase}[A-Z0-9_]*=" "$ENV_FILE"; then
			die "$ENV_FILE must not carry cohort membership (matched phrase ${phrase})"
		fi
	done
	if grep -Eq 'NCT[0-9]{8}' "$ENV_FILE"; then
		die "$ENV_FILE must not mention an NCT identifier"
	fi
}

assert_b0a_untouched() {
	# Fail loudly rather than silently sharing state with the B0a worker lane.
	[ "$STATE_ROOT" != "$B0A_STATE_ROOT" ] || die "state root collides with the B0a worker lane"
	[ "$ENV_FILE" != "$B0A_ENV_FILE" ] || die "env file collides with the B0a worker lane"
	[ "$ENV_FILE" != "$B0A_CONTROL_ENV_FILE" ] || die "env file collides with the B0a control lane"
	case "$CONFIG_ROOT" in
		"$B0A_STATE_ROOT"|"$B0A_STATE_ROOT"/*) die "config root is inside the B0a worker lane" ;;
	esac
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
	[ "$account_name" = "$SERVICE_USER" ] || die "unexpected fixed-cohort service identity"
	[ "$account_home" = "$STATE_ROOT" ] || die "$SERVICE_USER has an unexpected home directory"
	case "$account_shell" in
		*/nologin|*/false) ;;
		*) die "$SERVICE_USER must use a non-login shell" ;;
	esac
	# Least privilege: this identity must not inherit the B0a lane's group.
	if id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -qx macro-biocatalyst; then
		die "$SERVICE_USER must not be a member of the B0a macro-biocatalyst group"
	fi
}

provision_paths() {
	# Membership configuration is root-owned and read-only to the service.
	install -d -o root -g root -m 0755 "$CONFIG_ROOT"
	install -d -o root -g root -m 0755 "$MANIFEST_ROOT"
	# Private state belongs to the service identity and to nobody else.
	install -d -o root -g root -m 0755 "$STATE_ROOT"
	install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$RUN_ROOT"
	install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$RECEIPT_ROOT"
	install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$OPERATIONAL_ROOT"
	if [ -e "$ENV_FILE" ]; then
		chown root:root "$ENV_FILE"
		chmod 0600 "$ENV_FILE"
	fi
	if [ -L "$ACTIVE_POINTER" ]; then
		die "$ACTIVE_POINTER is a symlink; the active pointer must be a real file"
	fi
}

verify_paths() {
	local mode owner
	[ -d "$CONFIG_ROOT" ] || die "missing config root: $CONFIG_ROOT"
	[ -d "$MANIFEST_ROOT" ] || die "missing manifest root: $MANIFEST_ROOT"
	[ -f "$ENV_FILE" ] || die "missing root-owned environment file: $ENV_FILE"
	if [ -L "$ENV_FILE" ]; then
		die "$ENV_FILE must not be a symlink"
	fi
	owner="$(stat -c '%U:%G' "$ENV_FILE")"
	[ "$owner" = "root:root" ] || die "$ENV_FILE must be root:root (found $owner)"
	mode="$(stat -c '%a' "$ENV_FILE")"
	[ "$mode" = "600" ] || die "$ENV_FILE must be mode 0600 (found $mode)"
	assert_no_membership_in_env_file
	if ! grep -Eq '^BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED=[01][[:space:]]*$' "$ENV_FILE"; then
		die "$ENV_FILE must set BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED to 0 or 1"
	fi
	if ! grep -Eq '^BIOCATALYST_FIXED_COHORT_USER_AGENT=.+$' "$ENV_FILE"; then
		die "$ENV_FILE must set a non-empty BIOCATALYST_FIXED_COHORT_USER_AGENT contact string"
	fi
	if grep -Eq "^BIOCATALYST_FIXED_COHORT_USER_AGENT=([[:space:]]*|\"\"|'')$" "$ENV_FILE"; then
		die "$ENV_FILE must set a non-empty BIOCATALYST_FIXED_COHORT_USER_AGENT contact string"
	fi
	if [ -L "$ACTIVE_POINTER" ]; then
		die "$ACTIVE_POINTER must never be a symlink"
	fi
	if [ -e "$ACTIVE_POINTER" ]; then
		owner="$(stat -c '%U:%G' "$ACTIVE_POINTER")"
		[ "$owner" = "root:root" ] || die "$ACTIVE_POINTER must be root:root (found $owner)"
	fi
	# The B0a lane must be untouched by this provisioning.
	if [ -e "$B0A_ENV_FILE" ]; then
		owner="$(stat -c '%U:%G' "$B0A_ENV_FILE")"
		[ "$owner" = "root:root" ] || die "the B0a env file ownership changed unexpectedly"
	fi
}

verify_units() {
	if command -v systemd-analyze >/dev/null 2>&1; then
		systemd-analyze verify "$SERVICE_SOURCE" "$TIMER_SOURCE"
	else
		log "systemd-analyze unavailable; skipped unit verification"
	fi
}

install_units() {
	command -v systemctl >/dev/null 2>&1 || die "systemctl is required to install units"
	install -m 0644 "$SERVICE_SOURCE" "$SERVICE_DEST"
	install -m 0644 "$TIMER_SOURCE" "$TIMER_DEST"
	systemctl daemon-reload
	# Deliberately absent: systemctl enable, systemctl start.  Arming is an
	# operator act gated on the separate B1S2c decision.
	log "units installed and intentionally left disabled and unstarted"
}

reconcile_units() {
	# Reconciliation touches ONLY units that an operator already installed. A
	# routine production pull must never turn a partially configured collector
	# into an installed one, and must never change arming state.
	if [ ! -f "$SERVICE_DEST" ] || [ ! -f "$TIMER_DEST" ]; then
		log "fixed-cohort units are not installed; nothing to reconcile"
		return 0
	fi
	if cmp -s "$SERVICE_SOURCE" "$SERVICE_DEST" && cmp -s "$TIMER_SOURCE" "$TIMER_DEST"; then
		log "fixed-cohort units already match their sources"
		return 0
	fi
	verify_units || die "refusing unit reconciliation — systemd-analyze verify failed"
	local timer_was_enabled=0
	if systemctl is-enabled --quiet "$TIMER_UNIT" 2>/dev/null; then
		timer_was_enabled=1
	fi
	if ! cmp -s "$SERVICE_SOURCE" "$SERVICE_DEST"; then
		install -m 0644 "$SERVICE_SOURCE" "$SERVICE_DEST"
	fi
	if ! cmp -s "$TIMER_SOURCE" "$TIMER_DEST"; then
		install -m 0644 "$TIMER_SOURCE" "$TIMER_DEST"
	fi
	systemctl daemon-reload
	if [ "$timer_was_enabled" -eq 1 ]; then
		# Preserve, never create, arming state.
		systemctl restart "$TIMER_UNIT"
	fi
	log "fixed-cohort unit files reconciled without changing arming state"
}

mask_units() {
	command -v systemctl >/dev/null 2>&1 || die "systemctl is required to mask units"
	systemctl mask "$SERVICE_UNIT" "$TIMER_UNIT"
	log "both fixed-cohort units are masked; nothing can start them"
}

unmask_note() {
	cat <<'NOTE'
This script never unmasks or arms the fixed-cohort lane. An operator who has
completed the B1S2c arming decision runs, by hand:
  systemctl unmask macro-biocatalyst-fixed-cohort.timer macro-biocatalyst-fixed-cohort.service
  systemctl enable --now macro-biocatalyst-fixed-cohort.timer
NOTE
}

main() {
	local action="${1:---install}"

	case "$action" in
		--help|-h) usage; exit 0 ;;
		--install|--verify-prereqs|--reconcile|--mask|--unmask-note) ;;
		*) usage >&2; die "unknown argument: $action" ;;
	esac

	if [ "$action" = "--unmask-note" ]; then
		unmask_note
		exit 0
	fi

	[ "$(id -u)" -eq 0 ] || die "must run as root"
	[ -f "$SERVICE_SOURCE" ] || die "missing service source: $SERVICE_SOURCE"
	[ -f "$TIMER_SOURCE" ] || die "missing timer source: $TIMER_SOURCE"
	assert_b0a_untouched

	case "$action" in
		--verify-prereqs)
			verify_paths
			verify_units
			log "prerequisites verified; the timer remains disabled"
			;;
		--reconcile)
			reconcile_units
			;;
		--mask)
			mask_units
			;;
		--install)
			ensure_service_identity
			provision_paths
			assert_no_membership_in_env_file
			verify_units
			install_units
			log "populate $ENV_FILE (transport limits only), install a manifest, then run --verify-prereqs"
			log "arming is a separate operator act; this script does not perform it"
			;;
	esac
}

main "$@"
