#!/usr/bin/env bash
# Pull-IF-CHANGED refresh of the served site. Installed as /usr/local/bin/macro-update
# by setup.sh; run by a FREQUENT cron (every few min) + by hand. Cheap no-op when main
# hasn't moved, so it's safe to run often — that's what makes mastermind-x.com track
# main within minutes (the render.yml express lane + the nightly both land here fast)
# instead of waiting on a once-a-night pull.
set -euo pipefail
APP_DIR="/opt/macro"

git -C "$APP_DIR" fetch --depth 1 -q origin main
OLD=$(git -C "$APP_DIR" rev-parse HEAD)
NEW=$(git -C "$APP_DIR" rev-parse FETCH_HEAD)
[ "$OLD" = "$NEW" ] && exit 0   # nothing new — cheap no-op (frequent-cron safe)

CHANGED=$(git -C "$APP_DIR" diff --name-only "$OLD" "$NEW" 2>/dev/null || true)
git -C "$APP_DIR" reset --hard -q FETCH_HEAD

# Publish the served tree ATOMICALLY. `git reset --hard` above rewrites changed
# files IN PLACE (truncate-then-write), so if Caddy's root were the git work-tree
# it could hand out a 0-byte file mid-reset — and the CDN would cache that empty
# 200 (the 2026-07-03 white-page incident: a blank us_stocks/macro/china served
# for ~an hour from a poisoned EdgeOne edge entry). So the Caddy root is a SEPARATE
# dir OUTSIDE the git tree (see Caddyfile: root /opt/macro/site.served), refreshed
# here by rsync — whose per-file temp-write + rename() is atomic on the same
# filesystem, so a concurrent read sees either the whole old file or the whole new
# one, never a partial. --delete prunes pages removed upstream.
mkdir -p "$APP_DIR/site.served"
rsync -a --delete "$APP_DIR/site/" "$APP_DIR/site.served/"

# Caddyfile: reinstall + validate + reload ONLY when it actually changed (a bad
# config can never take the site down — reload is gated on `caddy validate`).
if ! cmp -s "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile; then
	install -m 0644 "$APP_DIR/app/deploy/Caddyfile" /etc/caddy/Caddyfile
	caddy validate --config /etc/caddy/Caddyfile && { systemctl reload caddy 2>/dev/null || systemctl restart caddy; }
fi

# macro-api: restart ONLY when its own code changed (avoid blipping /api on every
# site/ render commit). "Its own code" includes the engine modules /api/ask imports
# (ask_brain → cortex + llm_auth, cached in the running uvicorn after first call —
# without a restart an engine-side fix never goes live).
if echo "$CHANGED" | grep -qE '^(app/(main\.py|requirements\.txt|__init__\.py)|engine/neuralweb/(ask_brain|cortex)\.py|engine/llm_auth\.py)$'; then
	systemctl is-enabled macro-api >/dev/null 2>&1 && systemctl restart macro-api || true
fi

# admin console: restart ONLY when its own code changed, so the deployed panel at
# admin.mastermind-x.com tracks main automatically (config/secrets live in the
# untouched /etc/macro-admin.env, so a restart never loses them).
if echo "$CHANGED" | grep -qE '^admin/'; then
	systemctl is-enabled admin >/dev/null 2>&1 && systemctl restart admin || true
fi

echo "macro-update $(date -u +%FT%TZ) ${OLD:0:8}..$(git -C "$APP_DIR" rev-parse --short HEAD)"
