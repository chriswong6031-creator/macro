#!/usr/bin/env bash
# Idempotent provisioning for the mastermind-x.com static origin (DO droplet, Ubuntu).
# Serves the prebuilt site/ via Caddy behind Cloudflare. Safe to re-run.
#
# One-shot from a clean droplet (repo is public — no auth needed):
#   curl -fsSL https://raw.githubusercontent.com/chriswong6031-creator/macro/main/app/deploy/setup.sh | bash
# Or, after the repo is already cloned:  bash /opt/macro/app/deploy/setup.sh
set -euo pipefail

REPO_URL="https://github.com/chriswong6031-creator/macro.git"
APP_DIR="/opt/macro"
DOMAIN="mastermind-x.com"

log() { echo "[setup] $*"; }

log "[1/6] base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl git ufw gnupg rsync

log "[2/6] Caddy (official repo)"
if ! command -v caddy >/dev/null 2>&1; then
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
		| gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
		> /etc/apt/sources.list.d/caddy-stable.list
	apt-get update -y
	apt-get install -y caddy
fi

log "[3/6] clone/refresh repo (depth-1, public)"
mkdir -p "$(dirname "$APP_DIR")"
if [ -d "$APP_DIR/.git" ]; then
	git -C "$APP_DIR" fetch --depth 1 origin main
	git -C "$APP_DIR" reset --hard FETCH_HEAD
else
	git clone --depth 1 --branch main "$REPO_URL" "$APP_DIR"
fi
test -f "$APP_DIR/site/index.html" || { log "FATAL: $APP_DIR/site/index.html missing after clone"; exit 1; }

# Publish the served tree ATOMICALLY into a dir OUTSIDE the git work-tree, so the
# `git reset --hard` in update.sh can never expose a 0-byte file to Caddy/the CDN
# (2026-07-03 white-page incident). Caddy's root is $APP_DIR/site.served (see
# Caddyfile); it MUST exist + be populated before Caddy starts below, or the site
# 404s until the first cron pull. rsync is atomic per-file (temp-write + rename).
log "[3b/6] publish served tree -> $APP_DIR/site.served (atomic)"
mkdir -p "$APP_DIR/site.served"
rsync -a --delete "$APP_DIR/site/" "$APP_DIR/site.served/"

log "[4/6] install + validate Caddyfile"
install -m 0644 "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile
caddy fmt --overwrite /etc/caddy/Caddyfile || true
caddy validate --config /etc/caddy/Caddyfile

log "[5/6] firewall: SSH + HTTP/HTTPS"
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

log "[6/6] enable Caddy + fast pull-if-changed cron"
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy
install -m 0755 "$APP_DIR/app/deploy/update.sh" /usr/local/bin/macro-update
# Track main within minutes: pull-if-changed every 3 min (cheap no-op when unchanged),
# so render.yml's fast template renders AND the nightly data build reach the domain
# quickly — instead of a once-a-night pull. `|| true`: on a box with no crontab yet,
# `crontab -l`+`grep -v` both "fail" on empty input and would abort under
# `set -e -o pipefail` before the echo — keep them harmless.
{ crontab -l 2>/dev/null | grep -v 'macro-update' || true ; \
  echo "*/3 * * * * /usr/local/bin/macro-update >> /var/log/macro-update.log 2>&1" ; } | crontab -

# Rotate the cron + Caddy logs so they can never fill the droplet disk.
install -m 0644 "$APP_DIR/app/deploy/logrotate-macro-vps" /etc/logrotate.d/macro-vps 2>/dev/null || true

# Lock the web origin to Cloudflare IPs only (close the direct-to-origin bypass). Fail-open:
# a CF-fetch failure leaves provisioning intact rather than blocking the deploy.
bash "$APP_DIR/app/deploy/firewall-cloudflare.sh" || log "firewall step skipped (non-fatal)"

log "DONE — Caddy serving https://$DOMAIN from $APP_DIR/site.served (atomic mirror of $APP_DIR/site)"
log "HEAD: $(git -C "$APP_DIR" rev-parse --short HEAD)"
systemctl --no-pager status caddy | head -4 || true

# ── Site Access Gate runtime dir ─────────────────────────────────────────────
# The gate store lives at SITE_GATE_STATE (default /var/lib/macro-api/site_gate.json).
# /var/lib/macro-api is already used for the per-user quota ledger; ensure it exists
# with the correct permissions.  The store file itself is created on the first save
# via the admin panel (/api/site_gate/save); an absent file is treated as
# {enabled:false} → allow everyone (fail-open).
mkdir -p /var/lib/macro-api
chmod 700 /var/lib/macro-api
log "Runtime dir /var/lib/macro-api is present (SITE_GATE_STATE default lives here)."

# Optional: download the MaxMind GeoLite2-Country database for origin-side
# country detection (CDN header detection works without it).  Skipped when
# MAXMIND_LICENSE_KEY is absent.
if [ -n "${MAXMIND_LICENSE_KEY:-}" ]; then
    bash "$APP_DIR/app/deploy/geoip-setup.sh" || log "geoip-setup skipped (non-fatal)"
else
    log "MAXMIND_LICENSE_KEY not set — GeoIP country detection unavailable (CDN header still works)."
    log "See app/deploy/geoip-setup.sh for setup instructions."
fi
