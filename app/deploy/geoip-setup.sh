#!/usr/bin/env bash
# geoip-setup.sh — Download the MaxMind GeoLite2-Country database for the
# site-access gate (app/gate.py).  Idempotent; safe to re-run.
#
# The site-access gate works without this file — country detection falls back
# to the CDN header (EO-Client-IPCountry for EdgeOne, CF-IPCountry for
# Cloudflare) when the db is absent.  GeoIP is only needed when the CDN
# country header is unavailable or when you want origin-side verification.
#
# Prerequisites
# -------------
# 1. A (free) MaxMind account: https://www.maxmind.com/en/geolite2/signup
# 2. A licence key from: Account → Manage Licence Keys → Generate New Licence Key
#    (select the GeoLite2 database, NOT the commercial one).
# 3. Set MAXMIND_LICENSE_KEY in the environment before running this script, or in
#    /etc/macro-api.env and restart macro-api.service.
#
# Usage
# -----
#   MAXMIND_LICENSE_KEY=<your_key> bash /opt/macro/app/deploy/geoip-setup.sh
#   # or, from the repo:
#   bash app/deploy/geoip-setup.sh
#
# The db is written to $GEOIP_DB (default /var/lib/macro-api/GeoLite2-Country.mmdb).
# macro-api/gate.py reads from the same default; no restart needed — the gate
# re-opens the db lazily on the next request.
#
# Idempotency
# -----------
# If the file already exists and is newer than 7 days, the download is skipped.
# MaxMind updates GeoLite2 databases twice a week; a weekly re-run via cron is
# sufficient:
#   0 4 * * 0  MAXMIND_LICENSE_KEY=<key> bash /opt/macro/app/deploy/geoip-setup.sh
#              >> /var/log/geoip-setup.log 2>&1

set -euo pipefail

GEOIP_DB="${GEOIP_DB:-/var/lib/macro-api/GeoLite2-Country.mmdb}"
EDITION="GeoLite2-Country"
TMPDIR_BASE="$(dirname "$GEOIP_DB")"

log() { echo "[geoip-setup] $*"; }

# ── Check for licence key ─────────────────────────────────────────────────────
if [ -z "${MAXMIND_LICENSE_KEY:-}" ]; then
    log "MAXMIND_LICENSE_KEY is not set — skipping GeoIP db download."
    log "To enable country blocking via GeoIP:"
    log "  1. Create a free MaxMind account at https://www.maxmind.com/en/geolite2/signup"
    log "  2. Generate a licence key (Account → Manage Licence Keys)"
    log "  3. Add:  MAXMIND_LICENSE_KEY=<your_key>  to /etc/macro-api.env"
    log "  4. Re-run:  MAXMIND_LICENSE_KEY=<your_key> bash $0"
    log ""
    log "Country blocking via CDN header (EO-Client-IPCountry / CF-IPCountry)"
    log "works without GeoIP — see /api/gate/status for current detection source."
    exit 0
fi

# ── Skip if the db already exists and is fresh (< 7 days old) ────────────────
if [ -f "$GEOIP_DB" ]; then
    age_days=$(( ( $(date +%s) - $(date -r "$GEOIP_DB" +%s 2>/dev/null || echo 0) ) / 86400 ))
    if [ "$age_days" -lt 7 ]; then
        log "GeoIP db at $GEOIP_DB is ${age_days}d old — skipping download (< 7 days)."
        exit 0
    fi
    log "GeoIP db at $GEOIP_DB is ${age_days}d old — refreshing."
fi

# ── Download ──────────────────────────────────────────────────────────────────
mkdir -p "$TMPDIR_BASE"
TMPDIR_DL="$(mktemp -d "${TMPDIR_BASE}/.geoip-dl.XXXXXX")"

cleanup() { rm -rf "$TMPDIR_DL"; }
trap cleanup EXIT

URL="https://download.maxmind.com/app/geoip_download?edition_id=${EDITION}&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz"

log "Downloading $EDITION from MaxMind..."
curl -fsSL --max-time 120 "$URL" -o "${TMPDIR_DL}/${EDITION}.tar.gz"

log "Extracting..."
tar -xzf "${TMPDIR_DL}/${EDITION}.tar.gz" -C "$TMPDIR_DL"

# Find the .mmdb in the extracted directory
MMDB_SRC="$(find "$TMPDIR_DL" -name "*.mmdb" | head -1)"
if [ -z "$MMDB_SRC" ]; then
    log "ERROR: no .mmdb file found in the downloaded archive."
    exit 1
fi

# Atomic install (temp file in same dir + os.rename equivalent)
MMDB_TMP="${GEOIP_DB}.tmp.$$"
cp "$MMDB_SRC" "$MMDB_TMP"
mv "$MMDB_TMP" "$GEOIP_DB"

log "GeoIP db installed to $GEOIP_DB"
log "File size: $(du -sh "$GEOIP_DB" | cut -f1)"
log "Done.  macro-api gate will pick up the new db on the next request (no restart needed)."
