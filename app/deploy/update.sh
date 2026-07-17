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
# --min-size=1 is the 0-byte guard: an empty source file (interrupted checkout,
# disk-full, any future race this script hasn't met yet) is never transferred,
# so the last GOOD copy keeps serving — an empty page can't reach the CDN from
# here. site/ legitimately contains no empty files (verified 2026-07-11);
# revisit the flag if a deliberately-empty file ever ships.
mkdir -p "$APP_DIR/site.served"
rsync -a --delete --min-size=1 "$APP_DIR/site/" "$APP_DIR/site.served/"

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
		echo "macro-update: self-updated from repo"
	else
		echo "macro-update: refusing self-update — bash -n failed" >&2
	fi
fi

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
# untouched /etc/macro-admin.env, so a restart never loses them). "Its own code"
# includes the engine/lib modules the panels lazily import — cached in sys.modules
# after the first request, so without a restart an engine-side fix (e.g. a
# key_pool.py change to the Raw Key Usage join) never reaches the running panel;
# data files are read from disk per request and need no restart. Keep this list in
# sync when adding a lazy engine/lib import to an admin/ panel:
#   ai_cost/orchestrator_chat → lib/ai_costs; metabolism_panel → key_pool, throttle;
#   server manual-run gate → budget_gate; orchestrator_chat → ask_brain;
#   neural_web → support_map, orchestrator_log.
if echo "$CHANGED" | grep -qE '^(admin/.*|lib/ai_costs\.py|engine/neuralweb/(key_pool|ask_brain|support_map|orchestrator_log)\.py|engine/metabolism/(throttle|budget_gate)\.py)$'; then
	systemctl is-enabled admin >/dev/null 2>&1 && systemctl restart admin || true
fi

echo "macro-update $(date -u +%FT%TZ) ${OLD:0:8}..$(git -C "$APP_DIR" rev-parse --short HEAD)"
