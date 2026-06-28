#!/usr/bin/env bash
# Lock the web origin to Cloudflare: 80/443 accept ONLY Cloudflare's published IP ranges,
# so nobody can bypass Cloudflare by hitting the droplet IP directly (direct-origin scraping,
# attacks, or pulling the noindex product around the CF edge / WAF / DDoS protection).
# SSH (22) stays open (key-only — password auth is off). Macro outbound (git pull, Yahoo,
# Polygon) is unaffected (default allow outgoing).
#
# FAIL-OPEN by construction: CF ranges are fetched + validated BEFORE the firewall is touched,
# and `ufw reset` leaves ufw DISABLED until re-enabled — so any error leaves the box reachable
# (just unprotected), never locked out. A monthly cron re-runs this to track CF range changes.
set -euo pipefail
log() { echo "[fw] $*"; }
SELF="/opt/macro/app/deploy/firewall-cloudflare.sh"

log "fetch + validate Cloudflare IP ranges (BEFORE touching the firewall)"
V4=$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4)
V6=$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6 || true)   # v6 optional
[ "$(printf '%s\n' "$V4" | grep -c '/')" -ge 5 ] || { log "FATAL: CF v4 list looks wrong — aborting, firewall untouched"; exit 1; }

log "rebuild ufw: deny-in / allow-out, SSH open, 80+443 from Cloudflare only"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
for cidr in $V4 $V6; do
  ufw allow from "$cidr" to any port 80,443 proto tcp >/dev/null
done
ufw --force enable >/dev/null

log "monthly self-refresh cron (CF ranges change rarely)"
{ crontab -l 2>/dev/null | grep -v "firewall-cloudflare" || true ; \
  echo "0 4 1 * * $SELF >> /var/log/firewall.log 2>&1" ; } | crontab -

n=$(printf '%s\n%s\n' "$V4" "$V6" | grep -c '/' || true)
log "DONE — 80/443 limited to $n Cloudflare ranges; 22 open (key-only)"
