#!/usr/bin/env bash
# Slice 2 — deploy the FastAPI serving tier (macro-api) on the droplet.
# Builds a minimal venv (NOT the heavy engine stack), installs the serving and
# private Market Memory source/context/identity/breadth/technical/production-record/option-probe units, and starts their
# public-safe or API-inaccessible lanes.
# Idempotent. Run AFTER setup.sh (which installs the Caddyfile that proxies /api/* here).
#   bash /opt/macro/app/deploy/api-setup.sh
set -euo pipefail

APP_DIR="/opt/macro"
VENV="/opt/macro-api/.venv"
OPTIONS_API_FENCE_MARKER=/run/macro-api-market-memory-options-deny.ready
OPTIONS_RECIPROCAL_FENCE_MARKER=/run/macro-market-memory-options-reciprocal-deny.ready
log() { echo "[api-setup] $*"; }

# Serialize the manual provisioner with the three-minute updater. Both mutate
# the shared checkout/runtime and the same systemd boundary.
exec 9>/var/lock/macro-update.lock
flock 9
source "$APP_DIR/app/deploy/market-memory-options-unit-boundary.sh"
source "$APP_DIR/app/deploy/market-memory-options-runtime-fence.sh"
source "$APP_DIR/app/deploy/market-memory-options-dropin-migration.sh"

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

# A manual reconciliation may take long enough to overlap the daily probe.
# Invalidate the runtime API fence and disarm immediately; only the verified
# post-restart path below may recreate the marker and re-arm the timer.
disarm_option_lane() {
  local unit_file_state
  rm -f "$OPTIONS_API_FENCE_MARKER"
  rm -f "$OPTIONS_RECIPROCAL_FENCE_MARKER"
  if ! systemctl disable --now macro-market-memory-options.timer >/dev/null 2>&1; then
    if ! unit_absent_from_manager_and_disk \
      macro-market-memory-options.timer \
      /etc/systemd/system/macro-market-memory-options.timer; then
      log "cannot disarm the installed option-OI timer"
      return 1
    fi
  fi
  if [ -e /etc/systemd/system/macro-market-memory-options.timer ]; then
    unit_file_state=$(systemctl show -p UnitFileState --value \
      macro-market-memory-options.timer) || return 1
    case "$unit_file_state" in
      disabled|masked) ;;
      *) log "option-OI timer remains enabled"; return 1 ;;
    esac
  fi
  stop_unit_and_verify_inactive \
    macro-market-memory-options.timer \
    /etc/systemd/system/macro-market-memory-options.timer || {
    log "cannot stop the option-OI timer"
    return 1
  }
  stop_unit_and_verify_inactive \
    macro-market-memory-options.service \
    /etc/systemd/system/macro-market-memory-options.service || {
    log "cannot stop the option-OI writer"
    return 1
  }
}
disarm_option_lane
for reciprocal_profile in source context identity breadth technicals production-records; do
  reciprocal_timer="macro-market-memory-$reciprocal_profile.timer"
  reciprocal_service="macro-market-memory-$reciprocal_profile.service"
  if ! stop_unit_and_verify_inactive \
    "$reciprocal_timer" "/etc/systemd/system/$reciprocal_timer"; then
    log "cannot pause reciprocal Market Memory timer: $reciprocal_profile"
    exit 1
  fi
  if ! stop_unit_and_verify_inactive \
    "$reciprocal_service" "/etc/systemd/system/$reciprocal_service"; then
    log "cannot stop reciprocal Market Memory writer: $reciprocal_profile"
    exit 1
  fi
done

log "[1/5] python venv + minimal deps"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y python3-venv >/dev/null 2>&1 || true
mkdir -p /opt/macro-api
test -d "$VENV" || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP_DIR/app/requirements.txt"
sha256sum "$APP_DIR/app/requirements.txt" | cut -d' ' -f1 > /opt/macro-api/.requirements.sha256

log "[2/5] pinned Codex runtime"
bash "$APP_DIR/app/deploy/codex-runtime-setup.sh"

log "[3/5] systemd units + private Market Memory state"
# The unit's Market Memory bind is deliberately non-optional and read-only.
# Provision it before installation so a fresh host fails closed without making
# the first service start impossible.
install -d -m 0700 /var/lib/macro-market-memory
install -d -m 0700 /var/lib/macro-market-memory/public
install -d -m 0700 /var/lib/macro-market-memory/public/trusted-v1
install -d -m 0700 /var/lib/macro-market-memory/state
install -d -m 0700 /var/lib/macro-market-memory/state/sources
install -d -m 0700 /var/lib/macro-market-memory/state/context-projection
install -d -m 0700 /var/lib/macro-market-memory/state/identity-v1
install -d -m 0700 /var/lib/macro-market-memory/state/breadth-v1
install -d -m 0700 /var/lib/macro-market-memory/state/technicals-v1
install -d -m 0700 /var/lib/macro-market-memory/state/production-record-options-episode-v1
# W1A has no scheduled context writer. Establish and fully authenticate its
# empty generation spine explicitly before the first API process can become
# ready. This publishes metadata only; strict captures remain operator-owned.
if ! "$VENV/bin/python" "$APP_DIR/scripts/initialize_market_memory_w1a.py" \
  --repository-root "$APP_DIR" \
  --store /var/lib/macro-market-memory/public; then
  log "W1A public generation initialization failed; refusing API readiness"
  exit 1
fi
# Unit verification needs the static account and empty deny-anchor directories,
# but no credential or service-writable profile may exist until macro-api has
# restarted into its deny namespace.
bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" --identity-only
REVIEWED_UNIT_NAMES=(
  macro-api.service
  macro-market-memory-source.service macro-market-memory-source.timer
  macro-market-memory-context.service macro-market-memory-context.timer
  macro-market-memory-identity.service macro-market-memory-identity.timer
  macro-market-memory-breadth.service macro-market-memory-breadth.timer
  macro-market-memory-technicals.service macro-market-memory-technicals.timer
  macro-market-memory-production-records.service macro-market-memory-production-records.timer
  macro-market-memory-options.service macro-market-memory-options.timer
)
for reviewed_unit in "${REVIEWED_UNIT_NAMES[@]}"; do
  if ! mm_unit_repair_inputs_safe \
    "$APP_DIR/app/deploy/$reviewed_unit" \
    "/etc/systemd/system/$reviewed_unit"; then
    log "refusing unsafe unit repair input: $reviewed_unit"
    exit 1
  fi
done
systemd-analyze verify \
  "$APP_DIR/app/deploy/macro-api.service" \
  "$APP_DIR/app/deploy/macro-market-memory-source.service" \
  "$APP_DIR/app/deploy/macro-market-memory-source.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-context.service" \
  "$APP_DIR/app/deploy/macro-market-memory-context.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-identity.service" \
  "$APP_DIR/app/deploy/macro-market-memory-identity.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-breadth.service" \
  "$APP_DIR/app/deploy/macro-market-memory-breadth.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-technicals.service" \
  "$APP_DIR/app/deploy/macro-market-memory-technicals.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-production-records.service" \
  "$APP_DIR/app/deploy/macro-market-memory-production-records.timer" \
  "$APP_DIR/app/deploy/macro-market-memory-options.service" \
  "$APP_DIR/app/deploy/macro-market-memory-options.timer"
install -m 0644 "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-source.service" /etc/systemd/system/macro-market-memory-source.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-source.timer" /etc/systemd/system/macro-market-memory-source.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-context.service" /etc/systemd/system/macro-market-memory-context.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-context.timer" /etc/systemd/system/macro-market-memory-context.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-identity.service" /etc/systemd/system/macro-market-memory-identity.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-identity.timer" /etc/systemd/system/macro-market-memory-identity.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-breadth.service" /etc/systemd/system/macro-market-memory-breadth.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-breadth.timer" /etc/systemd/system/macro-market-memory-breadth.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-technicals.service" /etc/systemd/system/macro-market-memory-technicals.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-technicals.timer" /etc/systemd/system/macro-market-memory-technicals.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-production-records.service" /etc/systemd/system/macro-market-memory-production-records.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-production-records.timer" /etc/systemd/system/macro-market-memory-production-records.timer
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-options.service" /etc/systemd/system/macro-market-memory-options.service
install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-options.timer" /etc/systemd/system/macro-market-memory-options.timer
# Migrate only after the exact canonical API fragment is installed. Unknown
# files, symlinks, metadata drift, sibling drop-ins, or a noncanonical fragment
# abort setup with both writer families already stopped; nothing broad is
# deleted.
if [ -e "$MM_LEGACY_API_DROPIN_DIR" ] || [ -L "$MM_LEGACY_API_DROPIN_DIR" ]; then
  if ! mm_remove_exact_legacy_api_ollama_dropin \
    "$APP_DIR/app/deploy/macro-api.service" \
    /etc/systemd/system/macro-api.service; then
    log "refusing unsafe legacy macro-api drop-in migration"
    exit 1
  fi
fi
systemctl daemon-reload
[ "$(systemctl show -p NeedDaemonReload --value macro-api)" = no ] || {
  log "systemd still reports a stale macro-api unit after daemon-reload"
  exit 1
}

log "[4/5] initialize trusted context + start serving and retry timers"
systemctl enable macro-api >/dev/null 2>&1 || true
if ! mm_loaded_unit_ready \
  "$APP_DIR/app/deploy/macro-api.service" \
  /etc/systemd/system/macro-api.service macro-api.service; then
  log "macro-api effective unit boundary is not reviewed/current"
  exit 1
fi
for boundary_profile in source context identity breadth technicals production-records; do
  if ! mm_loaded_unit_ready \
    "$APP_DIR/app/deploy/macro-market-memory-$boundary_profile.service" \
    "/etc/systemd/system/macro-market-memory-$boundary_profile.service" \
    "macro-market-memory-$boundary_profile.service"; then
    log "reciprocal Market Memory unit is not reviewed/current: $boundary_profile"
    exit 1
  fi
  if ! mm_loaded_unit_ready \
    "$APP_DIR/app/deploy/macro-market-memory-$boundary_profile.timer" \
    "/etc/systemd/system/macro-market-memory-$boundary_profile.timer" \
    "macro-market-memory-$boundary_profile.timer"; then
    log "reciprocal Market Memory timer is not reviewed/current: $boundary_profile"
    exit 1
  fi
done
if ! mm_loaded_unit_ready \
  "$APP_DIR/app/deploy/macro-market-memory-options.service" \
  /etc/systemd/system/macro-market-memory-options.service \
  macro-market-memory-options.service || \
   ! mm_loaded_unit_ready \
  "$APP_DIR/app/deploy/macro-market-memory-options.timer" \
  /etc/systemd/system/macro-market-memory-options.timer \
  macro-market-memory-options.timer; then
  log "option-OI effective units are not reviewed/current"
  exit 1
fi
mm_write_reciprocal_fence_marker
# This oneshot initializes a complete empty trusted generation before strict
# projection. A source rejection is retryable and cannot make the API store
# incomplete or cause a nearest/current fallback.
systemctl start macro-market-memory-context.service || \
  log "trusted context projection failed closed; timer will retry"
systemctl start macro-market-memory-identity.service || \
  log "private identity observation accrual failed closed; timer will retry"
systemctl start macro-market-memory-breadth.service || \
  log "private breadth actual-output capture failed closed; timer will retry"
systemctl start macro-market-memory-technicals.service || \
  log "private technical actual-output capture failed closed; timer will retry"
systemctl start macro-market-memory-production-records.service || \
  log "private production-record capture failed closed; timer will retry"
PRE_API_PID=$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')
systemctl restart macro-api
POST_API_PID=$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')
if [[ ! "$POST_API_PID" =~ ^[1-9][0-9]*$ ]] || [ "$POST_API_PID" = "$PRE_API_PID" ]; then
  log "macro-api did not establish a verified new deny-namespace process"
  exit 1
fi
grep -Fxq 'InaccessiblePaths=/var/lib/macro-market-memory-options' /etc/systemd/system/macro-api.service
grep -Fxq 'InaccessiblePaths=/etc/macro-market-memory-options' /etc/systemd/system/macro-api.service
cmp -s "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service
mm_write_api_fence_marker

OPTIONS_CREDENTIAL_READY=0
if bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh"; then
  OPTIONS_CREDENTIAL_READY=1
else
  options_status=$?
  if [ "$options_status" -ne 2 ]; then
    exit "$options_status"
  fi
  log "option-OI canary credential absent; installing the fail-closed unit without arming it"
fi
if [ "$OPTIONS_CREDENTIAL_READY" -eq 1 ]; then
  systemctl start macro-market-memory-options.service || \
    log "private option-OI availability capture failed closed; weekday timer will retry"
fi
systemctl enable --now macro-market-memory-source.timer
systemctl enable --now macro-market-memory-context.timer
systemctl enable --now macro-market-memory-identity.timer
systemctl enable --now macro-market-memory-breadth.timer
systemctl enable --now macro-market-memory-technicals.timer
systemctl enable --now macro-market-memory-production-records.timer
if [ "$OPTIONS_CREDENTIAL_READY" -eq 1 ]; then
  if ! systemctl enable --now macro-market-memory-options.timer || \
     ! systemctl is-enabled macro-market-memory-options.timer >/dev/null 2>&1 || \
     ! systemctl is-active macro-market-memory-options.timer >/dev/null 2>&1; then
    disarm_option_lane
    log "option-OI timer failed verified enable; lane remains disarmed"
    exit 1
  fi
else
  disarm_option_lane
fi

log "[5/5] health check (local)"
sleep 2
curl -fsS http://127.0.0.1:8000/api/health && echo
log "DONE — macro-api on 127.0.0.1:8000 (Caddy proxies /api/* here)"
