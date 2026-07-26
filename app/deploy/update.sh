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
CHANGED=""
REPO_UPDATED=0
RECONCILED=0

if [ "$OLD" != "$NEW" ]; then
	CHANGED=$(git -C "$APP_DIR" diff --name-only "$OLD" "$NEW" 2>/dev/null || true)
	git -C "$APP_DIR" reset --hard -q FETCH_HEAD
	REPO_UPDATED=1

	# Publish the served tree ATOMICALLY. `git reset --hard` above rewrites
	# changed files IN PLACE, so Caddy serves a separate rsync target whose
	# per-file temp-write + rename keeps every visible file whole.
	mkdir -p "$APP_DIR/site.served"
	rsync -a --delete --min-size=1 "$APP_DIR/site/" "$APP_DIR/site.served/"
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

# macro-api systemd sandbox: keep the installed unit aligned with the reviewed
# repo copy. Validate before installation; a broken unit never replaces the
# running one. The restart decision below includes this path.
API_UNIT_UPDATED=0
if ! cmp -s "$APP_DIR/app/deploy/macro-api.service" /etc/systemd/system/macro-api.service; then
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
#   research_vault/        app/research.py imports catalog, corpus, download_quota,
#                          view_ratelimit, watermark (→ sidecar, r2_store) at MODULE
#                          level. Whole-package pattern on purpose: this is the
#                          vault's serving layer, so a new module added here is
#                          API-cached too and must not need a second fix. Omitting
#                          it silently froze download caps / anti-scrape limits —
#                          #3654 escaped only because it also touched app/research.py.
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
#   - Doctrine CONTENT (engine/neuralweb/doctrine/*.md): doctrine.py reloads the
#     .md files on mtime change, so prose-only edits go live with no restart.
#   - Data/artifact files read from disk per request.
#   - The nightly-only closure behind cortex.run() (constitution → qledger →
#     ai_desk → master_brain → china_*): the API imports cortex for its tool
#     schemas/implementations only and never calls run(), so those ~90 modules are
#     NOT in the API's sys.modules. Adding them would restart /api on nearly every
#     engine commit — exactly what this narrow list exists to prevent.
if [ "$API_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(app/.*\.py|app/requirements\.txt|app/deploy/macro-api\.service|config/site_access\.yml|engine/neuralweb/(ask_brain|cortex|brain_gateway|chart_perception|doctrine|envelope|key_pool|synapse)\.py|engine/(llm_auth|portfolio_brief|live_quotes|tushare_freshness)\.py|engine/research_vault/.*\.py|engine/context_index/(packet|fusion|gitinfo|lexical|structured)\.py|engine/marketing/(__init__|authority|chart_render|charter|claims|cmo|confluence_source|departments|economics|events|ledgers|opportunity_bus|publication|state)\.py|lib/(config|ai_costs|mastermind_response_log)\.py)$'; then
	systemctl is-enabled macro-api >/dev/null 2>&1 && systemctl restart macro-api || true
fi

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
#   engine/llm_auth.py     prophet.py deliberation-spend panel
#   marketing/             marketing.py's outbox approve/reject/decide endpoints →
#                          outbox + rejections. The other twelve ride the package
#                          __init__ (→ state → authority, charter, claims, cmo,
#                          departments, economics, events, ledgers,
#                          opportunity_bus, publication) — confirmed against a live
#                          interpreter's sys.modules. Named, not globbed: 34 of the
#                          48 marketing modules are nightly-only.
#   scripts/               marketing.py's publish dry-run → marketing_publisher
#
# Deliberately NOT here (they would blip the panel for nothing):
#   - site/ and data/ artifacts, read from disk per request.
#   - engine/neuralweb/cortex.py and the nightly lane behind it. The panel's only
#     entry into ask_brain is _post_filter_advice() (the advice guard); the
#     tool-schema/dispatch paths that lazily import cortex are never called from
#     admin, so cortex is absent from the panel's sys.modules. admin ships its own
#     tool dispatcher.
#   - The rest of engine/marketing (breaking_feed, seo_director, social_publisher,
#     …) — nightly-only, never imported by a panel.
if echo "$CHANGED" | grep -qE '^(admin/.*|lib/(ai_costs|mastermind_response_log)\.py|engine/llm_auth\.py|engine/neuralweb/(key_pool|ask_brain|support_map|orchestrator_log)\.py|engine/metabolism/(throttle|budget_gate)\.py|engine/marketing/(__init__|authority|charter|claims|cmo|departments|economics|events|ledgers|opportunity_bus|outbox|publication|rejections|state)\.py|scripts/marketing_publisher\.py)$'; then
	systemctl is-enabled admin >/dev/null 2>&1 && systemctl restart admin || true
fi

if [ "$REPO_UPDATED" -eq 1 ] || [ "$RECONCILED" -eq 1 ]; then
	echo "macro-update $(date -u +%FT%TZ) ${OLD:0:8}..$(git -C "$APP_DIR" rev-parse --short HEAD)"
fi
