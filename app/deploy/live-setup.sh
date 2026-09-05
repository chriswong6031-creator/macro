#!/usr/bin/env bash
# Install the VPS-owned live plane.
#
# Architecture:
#   macro-live-fast     every ~60s: official release watcher, display quotes,
#                       staggered overlay/risk/China state, 10-min heatmap
#   macro-live-snapshot every ~5m:  full-universe quote snapshot + US/HK baskets
#   macro-live-bars     hourly RTH: external intraday cache + flow pulse
#   macro-live-prophet  every ~5m in the ET session: Prophet Live provisional states
#                       (reads the two lanes above off disk, publishes R2 + the GATED
#                       live/prophet_live.json). Needs R2_* in /etc/macro-live.env.
#   macro-live-closepass every ~5m 20:00-23:59Z: mirrors the evening close-pass
#                       provisional board from R2 to the GATED
#                       live/us_board_provisional.json. Pure transport — it never
#                       computes. Needs R2_* in /etc/macro-live.env.
#   macro-live-breadth  every ~2m across the US session: the live intraday
#                       market-breadth poller (adv/dec/pa50/pa200/net_nh),
#                       writing the CANONICAL live/breadth.json this box serves.
#                       Reads the nightly-baked close caches off disk; a fault
#                       here can never take the served site down (own artifact
#                       only, own atomic rename). Was previously unowned by any
#                       VPS install — only the coarse GH-cron backstop ran it.
#
# All browser artifacts are atomically published to /var/lib/macro-live/public,
# outside /opt/macro and /opt/macro/site.served. Canonical history, forward ledgers,
# calibration and full renders remain on the nightly Mac/PC workflows.
set -euo pipefail

APP_DIR="/opt/macro"
VENV="$APP_DIR/.venv"
BASE_DIR="/var/lib/macro-live"
PUBLIC_DIR="$BASE_DIR/public"
LIVE_DIR="$PUBLIC_DIR/live"
log() { echo "[live-setup] $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "live-setup must run as root" >&2
  exit 1
fi

# Treat the first install as a transaction. Until the replacement timers are
# enabled AND legacy cron is retired, any error restores the old serving path.
# Existing installations are left in place on a rerun failure for diagnosis.
initial_install=1
if systemctl is-enabled macro-live-fast.timer >/dev/null 2>&1; then
  initial_install=0
fi
setup_complete=0
tmp_cron=""
fail_safe_exit() {
  rc=$?
  trap - EXIT
  if [ -n "$tmp_cron" ]; then
    rm -f "$tmp_cron"
  fi
  if [ "$rc" -ne 0 ] && [ "$initial_install" -eq 1 ] && [ "$setup_complete" -eq 0 ]; then
    log "first install failed; restoring legacy-only ownership"
    systemctl disable --now \
      macro-live-fast.timer \
      macro-live-snapshot.timer \
      macro-live-bars.timer >/dev/null 2>&1 || true
    systemctl stop \
      macro-live-fast.service \
      macro-live-snapshot.service \
      macro-live-bars.service >/dev/null 2>&1 || true
    if [ -d "$PUBLIC_DIR" ]; then
      failed_dir="$BASE_DIR/public.failed.$(date -u +%Y%m%dT%H%M%SZ)"
      mv "$PUBLIC_DIR" "$failed_dir" || true
      log "failed-install artifacts preserved at $failed_dir"
    fi
  fi
  exit "$rc"
}
trap fail_safe_exit EXIT

log "[1/6] runtime + live directories"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y python3-venv rsync >/dev/null 2>&1 || true
test -d "$VENV" || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
# boto3 is the Prophet Live lane's ONLY extra dependency: the armed pack, the previous
# pass's artifact and the event spool are R2 objects, and without it r2io.client()
# returns None, the lane reads the public mirror, publishes nothing and writes no
# served copy. Adding it here is what makes a re-run of this script arm the lane.
"$VENV/bin/pip" install -q pandas pyarrow numpy requests pyyaml jinja2 datasketch boto3
install -d -m 0755 \
  "$PUBLIC_DIR" "$LIVE_DIR" "$PUBLIC_DIR/marketdata" \
  "$BASE_DIR/state" "$BASE_DIR/data" "$APP_DIR/site/live"

log "[2/6] environment"
if [ ! -e /etc/macro-live.env ]; then
  install -m 0600 /dev/null /etc/macro-live.env
fi
chmod 0600 /etc/macro-live.env
if ! grep -q '^MACRO_LIVE_DIR=' /etc/macro-live.env; then
  {
    echo "MACRO_LIVE_DIR=$LIVE_DIR"
    echo "MACRO_LIVE_STATE_DIR=$BASE_DIR/state"
    echo "MACRO_LIVE_DATA_DIR=$BASE_DIR/data"
  } >> /etc/macro-live.env
fi

# R2 credential seeding — the INITIATING FAULT of the 2026-07-30..08-26 US
# Prophet Live force majeure (27 days dark, exit 0 the whole time): this file
# documented "Needs R2_* in /etc/macro-live.env" above but never wrote them,
# and nothing verified the precondition before macro-live-prophet went live.
# /etc/macro-api.env already carries the same R2_* keys for the API's own R2
# reads, so they are durably re-seeded here instead of typed twice by an
# operator. Each key is guarded by ITS OWN presence check in the DESTINATION
# file (the sentinel style the MACRO_LIVE_DIR block above uses), so this is
# safe to run repeatedly: a rerun, or an operator who already set one key by
# hand, never overwrites a value already there, and a box seeded with only
# some of the four keys self-heals the rest on the next run instead of being
# stuck half-seeded forever. NEVER logs a secret VALUE — only a count of keys
# newly copied and, on a gap, which key NAMES are missing — because this
# script's stdout lands in journalctl, which is not a secret store.
R2_SEEDED_COUNT=0
R2_SEED_MISSING=()
for R2_KEY in R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET; do
  if grep -q "^${R2_KEY}=" /etc/macro-live.env; then
    continue
  fi
  if [ -r /etc/macro-api.env ] && grep -q "^${R2_KEY}=" /etc/macro-api.env; then
    grep "^${R2_KEY}=" /etc/macro-api.env | tail -n 1 >> /etc/macro-live.env
    R2_SEEDED_COUNT=$((R2_SEEDED_COUNT + 1))
  else
    R2_SEED_MISSING+=("$R2_KEY")
  fi
done
chmod 0600 /etc/macro-live.env
log "R2 credential seed: ${R2_SEEDED_COUNT} key(s) newly copied from /etc/macro-api.env"
if [ "${#R2_SEED_MISSING[@]}" -gt 0 ]; then
  log "WARNING: R2 credentials are INCOMPLETE — macro-live-prophet and macro-live-closepass will read the public mirror and publish NOTHING until this is fixed (this exact gap produced the 2026-07-30..08-26 force-majeure: 27 days dark, exit 0 throughout)."
  log "WARNING: missing key(s), absent from BOTH /etc/macro-live.env and /etc/macro-api.env: ${R2_SEED_MISSING[*]}"
  log "WARNING: OPERATOR ACTION REQUIRED — add the missing key(s) to /etc/macro-api.env (preferred; shared with the API's own R2 reads) or directly to /etc/macro-live.env (must stay mode 0600), then re-run this script."
fi

log "[3/6] systemd services + timers"
unit_sources=()
for unit in \
  macro-live-fast.service macro-live-fast.timer \
  macro-live-snapshot.service macro-live-snapshot.timer \
  macro-live-bars.service macro-live-bars.timer \
  macro-live-prophet.service macro-live-prophet.timer \
  macro-live-closepass.service macro-live-closepass.timer \
  macro-live-breadth.service macro-live-breadth.timer
do
  unit_sources+=("$APP_DIR/app/deploy/$unit")
done
systemd-analyze verify "${unit_sources[@]}"
for unit_source in "${unit_sources[@]}"
do
  unit=$(basename "$unit_source")
  install -m 0644 "$APP_DIR/app/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload

log "[4/6] smoke test publication + fast lane"
# Keep the legacy cron writer in place until the replacement has proven that it
# can publish successfully. A failed install therefore leaves the old live path
# intact instead of creating an outage.
set +e
systemctl start macro-live-fast.service
smoke_rc=$?
set -e
if [ "$smoke_rc" -ne 0 ]; then
  log "smoke test failed; recent service log:"
  journalctl -u macro-live-fast.service -n 30 --no-pager
  exit "$smoke_rc"
fi
test -s "$LIVE_DIR/orchestrator_status.json"
test -s "$LIVE_DIR/quotes.json"
"$VENV/bin/python" -c \
  'import json,sys; d=json.load(open(sys.argv[1])); assert int((d.get("meta") or {}).get("resolved") or 0) >= 5' \
  "$LIVE_DIR/quotes.json"

log "[5/6] enable replacement timers"
# macro-live-prophet, macro-live-closepass and macro-live-breadth are armed here too,
# but none of the three is part of the fail-safe smoke transaction above: they consume
# what the three lanes publish (or, for breadth, the nightly-baked close caches) and
# write only their own runtime artifacts, so a fault in any of them can never take the
# served site down.
systemctl enable --now \
  macro-live-fast.timer \
  macro-live-snapshot.timer \
  macro-live-bars.timer \
  macro-live-prophet.timer \
  macro-live-closepass.timer \
  macro-live-breadth.timer >/dev/null

log "[6/6] retire legacy cron writer"
tmp_cron=$(mktemp)
crontab -l 2>/dev/null | grep -v "macro-live\\|build_live_overlay" > "$tmp_cron" || true
crontab "$tmp_cron"
rm -f "$tmp_cron"
tmp_cron=""

setup_complete=1
trap - EXIT
log "DONE — live plane installed"
systemctl list-timers \
  macro-live-fast.timer macro-live-snapshot.timer macro-live-bars.timer \
  macro-live-prophet.timer macro-live-closepass.timer macro-live-breadth.timer \
  --no-pager
log "After production freshness is verified, set GitHub repository variable VPS_LIVE_PRIMARY=true."
