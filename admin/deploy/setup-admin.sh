#!/usr/bin/env bash
# Idempotent provisioning for the deployed Admin console at admin.mastermind-x.com.
# Run as root ON THE VPS after /opt/macro is up to date:
#   bash /opt/macro/admin/deploy/setup-admin.sh
#
# Prereqs handled elsewhere: the DNS A record (admin -> 146.190.142.17, grey-cloud)
# and the secrets file /etc/macro-admin.env (created separately — never in the repo).
set -euo pipefail
APP_DIR=/opt/macro
VENV="$APP_DIR/.venv"
ENV_FILE=/etc/macro-admin.env
log() { echo "[admin-setup] $*"; }

test -d "$APP_DIR/admin" || { log "FATAL: $APP_DIR/admin missing (repo not cloned?)"; exit 1; }
test -x "$VENV/bin/python" || { log "FATAL: $VENV/bin/python missing"; exit 1; }

log "[1/5] python deps (pyyaml, requests, boto3, jsonschema)"
# boto3 backs the AI Response Logs tab's Refresh-from-R2 (lib/mastermind_response_log
# lazily imports it and no-ops gracefully when absent — creds present + no boto3 is
# a SILENT dead refresh, found the hard way 2026-07-26).
"$VENV/bin/python" - <<'PY' || "$VENV/bin/pip" install --quiet --disable-pip-version-check pyyaml requests boto3 jsonschema==4.26.0
import importlib.util as u, sys
sys.exit(0 if all(u.find_spec(m) for m in ("yaml", "requests", "boto3", "jsonschema")) else 1)
PY

log "[2/5] secrets file"
if [ ! -f "$ENV_FILE" ]; then
	umask 077
	cat > "$ENV_FILE" <<EOF
# macro-admin service env — ROOT-ONLY (chmod 600). Secrets; never commit.
ADMIN_DEPLOYED=1
# REQUIRED — the console refuses to start in deployed mode without this:
ADMIN_PASSWORD=
# Persist this so signed sessions survive a restart (any long random string):
ADMIN_SESSION_SECRET=$("$VENV/bin/python" -c "import secrets;print(secrets.token_hex(32))")
# Proves to the origin that a request came through the CDN edge, so the per-client
# login lockout can key on the real visitor instead of the shared edge IP. Inert until
# the EdgeOne console injects this same value as the X-MM-Edge-Auth origin-pull header
# (app/deploy/README.md "Admin per-client identity behind the edge"). ASCII on purpose:
# http.server decodes headers as latin-1, so a non-ASCII secret could never match.
ADMIN_EDGE_SECRET=$("$VENV/bin/python" -c "import secrets;print(secrets.token_hex(24))")
# Optional integrations (panels degrade gracefully until set):
SUPABASE_ACCESS_TOKEN=
# Required for the owner-private Prophet Trade Memory panel:
SUPABASE_OPERATOR_USER_ID=
# UMAMI_API_KEY=
# GH_TOKEN=
EOF
	chmod 600 "$ENV_FILE"
	log "  created $ENV_FILE skeleton — FILL IN ADMIN_PASSWORD before the panel is usable"
else
	log "  $ENV_FILE exists — left untouched"
fi

# Backfill keys added after a box was first provisioned. The skeleton above is only
# written when the file is ABSENT, so without this an existing VPS never gains a new
# setting and the feature stays silently inert there — which is exactly what happened
# to ADMIN_EDGE_SECRET. Append-only and idempotent: an operator-set value is never
# touched, and this must never rewrite ADMIN_PASSWORD or ADMIN_SESSION_SECRET.
if ! grep -q '^ADMIN_EDGE_SECRET=' "$ENV_FILE" 2>/dev/null; then
	umask 077
	{
		echo ""
		echo "# Edge attestation for the admin per-client login lockout — see"
		echo "# app/deploy/README.md \"Admin per-client identity behind the edge\"."
		echo "# Inert until the EdgeOne console sends it as X-MM-Edge-Auth on origin-pull."
		echo "ADMIN_EDGE_SECRET=$("$VENV/bin/python" -c "import secrets;print(secrets.token_hex(24))")"
	} >> "$ENV_FILE"
	chmod 600 "$ENV_FILE"
	log "  backfilled ADMIN_EDGE_SECRET into $ENV_FILE (still needs the EdgeOne console rule)"
fi

log "[3/5] systemd unit"
install -m 0644 "$APP_DIR/admin/deploy/admin.service" /etc/systemd/system/admin.service
systemctl daemon-reload

log "[4/5] Caddy (install repo Caddyfile if changed, validate, reload)"
if ! cmp -s "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile; then
	install -m 0644 "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy 2>/dev/null || systemctl restart caddy

log "[5/5] enable + (re)start admin.service"
systemctl enable admin.service >/dev/null 2>&1 || true
systemctl restart admin.service
sleep 1
systemctl --no-pager status admin.service | head -5 || true
log "local probe:"
curl -s -o /dev/null -w "  127.0.0.1:8787/healthz -> %{http_code}\n" http://127.0.0.1:8787/healthz || true
log "DONE — https://admin.mastermind-x.com (allow ~30s for the first Let's Encrypt cert)"
