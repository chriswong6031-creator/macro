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

	# Press properties (D14 W1.5) — same atomic-publish contract as site.served,
	# and for the same reason: `git reset --hard` above rewrites changed files IN
	# PLACE, so Caddy must serve a separate rsync target whose per-file temp-write
	# + rename keeps every visible file whole. --min-size=1 refuses to publish a
	# 0-byte file over a good one (the 2026-07-03 white-page incident).
	#
	# The [ -d ] guards are load-bearing, not defensive noise: these trees are
	# built by scripts/build_press_properties.py and may legitimately not exist
	# yet on a box that pulled main before they landed. Without the guard, rsync
	# of a missing source under `set -e` aborts the whole update run — and this
	# script is what keeps the MAIN site tracking main.
	#
	# The Caddy vhosts that serve these roots stay COMMENTED until the cutover
	# (see the marked block in app/deploy/Caddyfile), so syncing them early is
	# free: the files land, nothing serves them, and cutover day is a config flip
	# rather than a first-ever data copy.
	if [ -d "$APP_DIR/properties/news" ]; then
		mkdir -p "$APP_DIR/press_news.served"
		rsync -a --delete --min-size=1 "$APP_DIR/properties/news/" "$APP_DIR/press_news.served/"
	fi
	if [ -d "$APP_DIR/properties/research" ]; then
		mkdir -p "$APP_DIR/press_research.served"
		rsync -a --delete --min-size=1 "$APP_DIR/properties/research/" "$APP_DIR/press_research.served/"
	fi
fi

# Runtime-only company-logo configuration. The committed file is deliberately
# empty; the browser-safe Logo.dev publishable token lives in the root-readable
# VPS env and is materialized only into the served tree after every rsync. The
# server-side secret key is neither required nor accepted here.
LOGO_DEV_TOKEN=""
if [ -r /etc/macro-api.env ]; then
	LOGO_DEV_TOKEN=$(sed -n 's/^LOGO_DEV_PUBLISHABLE_KEY=//p' /etc/macro-api.env | tail -n 1)
fi
case "$LOGO_DEV_TOKEN" in
	pk_*) ;;
	*) LOGO_DEV_TOKEN="" ;;
esac
case "$LOGO_DEV_TOKEN" in
	*[!A-Za-z0-9_-]*) LOGO_DEV_TOKEN="" ;;
esac
mkdir -p "$APP_DIR/site.served"
LOGO_CONFIG_TMP=$(mktemp "$APP_DIR/site.served/.logo_config.XXXXXX")
printf 'window.MMX_LOGO_DEV_TOKEN = window.MMX_LOGO_DEV_TOKEN || "%s";\n' "$LOGO_DEV_TOKEN" > "$LOGO_CONFIG_TMP"
chmod 0644 "$LOGO_CONFIG_TMP"
if ! cmp -s "$LOGO_CONFIG_TMP" "$APP_DIR/site.served/logo_config.js"; then
	mv -f "$LOGO_CONFIG_TMP" "$APP_DIR/site.served/logo_config.js"
else
	rm -f "$LOGO_CONFIG_TMP"
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

# Codex CLI: keep the provider runtime pinned and self-healing just like the
# reviewed systemd units below. Authentication is durable VPS state under
# /var/lib/macro-codex and is never copied from or written into git.
if ! bash "$APP_DIR/app/deploy/codex-runtime-setup.sh" --quiet; then
	echo "macro-update: Codex runtime reconciliation failed; Claude/DeepSeek fallbacks remain available" >&2
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

# Serving dependencies: reconcile against a content stamp on every cron pass,
# not only the first pull that changed requirements.txt. A transient PyPI error
# therefore retries next tick, and the API never restarts into code whose declared
# dependencies failed to install. api-setup.sh writes the same stamp on provision.
API_DEPS_UPDATED=0
API_DEPS_OK=1
API_REQ_STAMP=/opt/macro-api/.requirements.sha256
API_REQ_HASH=$(sha256sum "$APP_DIR/app/requirements.txt" | cut -d' ' -f1)
API_INSTALLED_REQ_HASH=$(cat "$API_REQ_STAMP" 2>/dev/null || true)
if [ "$API_REQ_HASH" != "$API_INSTALLED_REQ_HASH" ]; then
	if [ -x /opt/macro-api/.venv/bin/pip ] \
		&& /opt/macro-api/.venv/bin/pip install -q -r "$APP_DIR/app/requirements.txt"; then
		API_REQ_TMP=$(mktemp /opt/macro-api/.requirements.XXXXXX)
		printf '%s\n' "$API_REQ_HASH" > "$API_REQ_TMP"
		chmod 0644 "$API_REQ_TMP"
		mv -f "$API_REQ_TMP" "$API_REQ_STAMP"
		API_DEPS_UPDATED=1
		RECONCILED=1
		echo "macro-update: macro-api dependencies reconciled"
	else
		API_DEPS_OK=0
		echo "macro-update: macro-api dependency reconciliation FAILED; keeping the running API" >&2
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
#   codex_provider/runner  llm_auth's request-time Codex fallback imports both;
#                          either module stays cached after the first Codex turn
#   research_vault/        app/research.py imports catalog, corpus, download_quota,
#                          view_ratelimit, watermark (→ sidecar, r2_store) at MODULE
#                          level. Whole-package pattern on purpose: this is the
#                          vault's serving layer, so a new module added here is
#                          API-cached too and must not need a second fix. Omitting
#                          it silently froze download caps / anti-scrape limits —
#                          #3654 escaped only because it also touched app/research.py.
#   fundamental_forensics/ app/forensics.py imports private_state through the
#                          package, whose __init__ loads the pure kernel modules;
#                          all are therefore pinned in macro-api sys.modules.
#   capital_structure/*    app/capital_structure.py imports projection at module
#                          load; projection and its package __init__ pull the
#                          event spine, normalized document-term kernel, and
#                          source-identity helpers into sys.modules. All stay
#                          pinned until macro-api restarts. Named narrowly so
#                          nightly-only compilers do not blip the serving plane.
#   government_revenue/*   app/government_revenue.py imports workspace through
#                          the non-inert package __init__, which loads the award,
#                          dossier, exact entity-resolution, federation,
#                          freshness, metric, opportunity, PIT, budget-program,
#                          IDV-dossier, and subaward-dossier helpers.
#                          These serving-plane modules remain cached for the
#                          life of macro-api and must advance with a deploy.
#   company_intelligence/* app/company_intelligence.py imports the verified
#                          reader's public artifact contract.  Importing this
#                          package executes its non-inert __init__, which loads
#                          contracts, health, and views; all are pinned in the
#                          API process for the lifetime of the public ticker
#                          context route.
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
#   - Doctrine CONTENT (engine/neuralweb/doctrine/*.md AND analyst/*.md): both
#     libraries reload the .md files on mtime change, so prose-only edits go
#     live with no restart.
#   - Data/artifact files read from disk per request.
#   - The nightly-only closure behind cortex.run() (constitution → qledger →
#     ai_desk → master_brain → china_*): the API imports cortex for its tool
#     schemas/implementations only and never calls run(), so those ~90 modules are
#     NOT in the API's sys.modules. Adding them would restart /api on nearly every
#     engine commit — exactly what this narrow list exists to prevent.
if [ "$API_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(app/.*\.py|app/requirements\.txt|app/deploy/macro-api\.service|config/site_access\.yml|engine/neuralweb/(ask_brain|cortex|brain_gateway|chart_perception|chat_plain_words|company_intelligence_reader|doctrine|analyst_doctrine|market_packet|brain_market_intel|brain_analogues|brain_curve|brain_user_memory|envelope|key_pool|synapse)\.py|engine/(codex_provider|llm_auth|portfolio_brief|live_quotes|tushare_freshness)\.py|engine/codex_lane/runner\.py|engine/research_vault/.*\.py|engine/fundamental_forensics/.*\.py|engine/biocatalyst/.*\.py|engine/sector_intelligence/.*\.py|engine/company_intelligence/.*\.py|engine/capital_structure/(__init__|document_terms|event_spine|projection|source_identity)\.py|engine/government_revenue/(__init__|award_events|budget_program|dossiers|entity_resolution|federation|freshness|idv_dossiers|metrics|opportunities|point_in_time|subaward_dossiers|workspace)\.py|engine/context_index/(packet|fusion|gitinfo|lexical|structured)\.py|engine/marketing/(__init__|authority|chart_render|charter|claims|cmo|confluence_source|departments|economics|events|ledgers|opportunity_bus|publication|state)\.py|lib/(config|ai_costs|mastermind_response_log|user_prefs|tiers)\.py)$' || [ "$API_DEPS_UPDATED" -eq 1 ]; then
	# Verified restart, not fire-and-forget: on 2026-07-30 the old one-liner
	# (`... && systemctl restart macro-api || true`) left the API on its 5-hour-old
	# PID after a matching deploy, and the `|| true` destroyed every trace of why.
	# Log the PID transition, and retry once when the restart failed or the PID
	# provably did not change — all output lands in macro-update.log.
	if [ "$API_DEPS_OK" -ne 1 ]; then
		echo "macro-update: macro-api restart skipped because dependency reconciliation failed" >&2
	elif systemctl is-enabled macro-api >/dev/null 2>&1; then
		PRE_PID="$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')"
		API_RESTART_RC=0
		systemctl restart macro-api || API_RESTART_RC=$?
		POST_PID="$(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')"
		if [ "$API_RESTART_RC" -ne 0 ] || { [ "$POST_PID" = "$PRE_PID" ] && [ "$POST_PID" != "?" ]; }; then
			echo "macro-api restart ANOMALY rc=$API_RESTART_RC pid $PRE_PID -> $POST_PID; retrying once"
			sleep 2
			systemctl restart macro-api || echo "macro-api restart RETRY FAILED rc=$?"
			echo "macro-api post-retry pid $(systemctl show -p MainPID --value macro-api 2>/dev/null || echo '?')"
		else
			echo "macro-api restarted pid $PRE_PID -> $POST_PID"
		fi
	fi
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

# PROPHET LIVE evaluator lane (research/PROPHET_LIVE_INTRADAY_SIGNALS_MASTERPLAN_BY_FABLE.md
# §4.2a). Its own block, not a fourth entry in the list above, for two reasons: the
# three lanes there are ONE orchestrator invoked with three --lane arguments, and
# widening that regex would restart all three timers whenever this unrelated unit
# changed. Same narrow allow-list discipline — exactly the two paths this lane owns.
#
# Unlike the block above it also arms itself, because go-live for this program is a
# REPO COMMIT and nothing else: the unit did not exist when live-setup.sh was last run
# on the box, so a CHANGED-only trigger would install a timer that nobody ever enables.
# `enable --now` on an already-enabled, already-active timer is a systemd no-op, and
# the absent-file clause makes the block self-healing when an earlier tick's
# systemd-analyze failed or an operator removed the unit (macro-update installing it
# twice must be, and is, a no-op).
#
# The live plane must already exist (macro-live-fast.timer enabled): this lane reads
# what those lanes publish, so on any host without them it would have nothing to read.
# That guard is also what keeps this block inert on a box that is not the VPS.
#
# The .service is NEVER restarted. It is a oneshot — `systemctl restart` would RUN a
# pass out of band, off the ET-windowed schedule, with the R2 debounce predecessor
# from whenever the last legitimate tick was. Only the timer is (re)armed.
if systemctl is-enabled macro-live-fast.timer >/dev/null 2>&1 && \
   { echo "$CHANGED" | grep -qE '^app/deploy/macro-live-prophet\.(service|timer)$' || \
     [ ! -f /etc/systemd/system/macro-live-prophet.timer ]; }; then
	PROPHET_UNIT_SOURCES=(
		"$APP_DIR/app/deploy/macro-live-prophet.service"
		"$APP_DIR/app/deploy/macro-live-prophet.timer"
	)
	if systemd-analyze verify "${PROPHET_UNIT_SOURCES[@]}"; then
		PROPHET_UNIT_UPDATED=0
		for UNIT_SOURCE in "${PROPHET_UNIT_SOURCES[@]}"; do
			UNIT=$(basename "$UNIT_SOURCE")
			if ! cmp -s "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"; then
				install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"
				PROPHET_UNIT_UPDATED=1
			fi
		done
		if [ "$PROPHET_UNIT_UPDATED" -eq 1 ]; then
			systemctl daemon-reload
			systemctl restart macro-live-prophet.timer 2>/dev/null || true
			RECONCILED=1
			echo "macro-update: macro-live-prophet units updated"
		fi
		systemctl enable --now macro-live-prophet.timer >/dev/null 2>&1 || \
			echo "macro-update: macro-live-prophet.timer could not be enabled" >&2
	else
		echo "macro-update: refusing macro-live-prophet unit update — systemd-analyze verify failed" >&2
	fi
fi

# PRESS-FEEDS is a long-running daemon, unlike the oneshot live-plane timers
# above. Arming remains an explicit operator choice: this block neither installs
# an absent unit nor enables/starts an inactive one. Once the operator has
# installed it, however, the reviewed unit must track main and an ACTIVE daemon
# must restart when import-cached code changes; otherwise a merged press-lane fix
# lands on disk while the old Python process runs forever.
PRESS_UNIT_UPDATED=0
if [ -f /etc/systemd/system/marketing-press-feeds.service ] && \
   ! cmp -s "$APP_DIR/app/deploy/marketing-press-feeds.service" /etc/systemd/system/marketing-press-feeds.service; then
	if systemd-analyze verify "$APP_DIR/app/deploy/marketing-press-feeds.service"; then
		install -m 0644 "$APP_DIR/app/deploy/marketing-press-feeds.service" /etc/systemd/system/marketing-press-feeds.service
		systemctl daemon-reload
		PRESS_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: marketing-press-feeds systemd sandbox updated"
	else
		echo "macro-update: refusing marketing-press-feeds unit update — systemd-analyze verify failed" >&2
	fi
fi

# BioCatalyst B1 is a separate source-canonical lane.  A routine production
# pull must never install, enable, or start it: doing so could turn a partially
# configured evidence collector live.  Reconcile only a fully operator-installed
# worker pair and dedicated runtime. The root-only retention heartbeat units are
# copied beside that pair but remain dormant unless separately armed. Dependencies are built in a versioned
# staging virtualenv and verified before one atomic current-symlink swap. No
# live runtime is ever pip-mutated, and a failed candidate leaves the previous
# runtime and timer arming state untouched.
BIOCATALYST_UNITS_INSTALLED=0
if [ -f /etc/systemd/system/macro-biocatalyst.service ] && \
   [ -f /etc/systemd/system/macro-biocatalyst.timer ]; then
	BIOCATALYST_UNITS_INSTALLED=1
fi

BIOCATALYST_RUNTIME_UPDATED=0
BIOCATALYST_RUNTIME_READY=0
if [ "$BIOCATALYST_UNITS_INSTALLED" -eq 1 ] && \
   [ -d /opt/macro-biocatalyst ] && \
   { [ -L /opt/macro-biocatalyst/current ] || \
     [ -x /opt/macro-biocatalyst/.venv/bin/python ]; } && \
   [ -f "$APP_DIR/app/deploy/biocatalyst-requirements.txt" ] && \
   [ -f "$APP_DIR/app/deploy/biocatalyst-runtime.sh" ]; then
	BIOCATALYST_REQUIREMENTS_HASH="$(sha256sum "$APP_DIR/app/deploy/biocatalyst-requirements.txt" | awk '{print $1}')"
	BIOCATALYST_INSTALLED_HASH=""
	if bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --verify; then
		BIOCATALYST_INSTALLED_HASH="$(awk 'NR == 1 { print $1 }' /opt/macro-biocatalyst/current/.requirements.sha256)"
		if [ "$BIOCATALYST_REQUIREMENTS_HASH" = "$BIOCATALYST_INSTALLED_HASH" ]; then
			BIOCATALYST_RUNTIME_READY=1
		fi
	fi
	if [ "$BIOCATALYST_RUNTIME_READY" -ne 1 ]; then
		if bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --install \
			"$APP_DIR/app/deploy/biocatalyst-requirements.txt"; then
			BIOCATALYST_RUNTIME_READY=1
			BIOCATALYST_RUNTIME_UPDATED=1
			RECONCILED=1
			echo "macro-update: BioCatalyst isolated runtime atomically reconciled without changing arming state"
		else
			echo "macro-update: BioCatalyst staged runtime failed; previous runtime remains selected" >&2
		fi
	fi
fi

# Reconcile unit files only after the runtime referenced by the reviewed service
# has passed verification. Preserve both timers' operator-controlled arming state.
BIOCATALYST_UNIT_UPDATED=0
if [ "$BIOCATALYST_UNITS_INSTALLED" -eq 1 ] && \
   { ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.service" /etc/systemd/system/macro-biocatalyst.service || \
     ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.timer" /etc/systemd/system/macro-biocatalyst.timer || \
     ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.service || \
     ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer; }; then
	# Capture arming before copying a new unit. In particular, a newly introduced
	# heartbeat timer must remain absent/disabled after reconciliation rather than
	# becoming an accidental activation path merely because its source now exists.
	BIOCATALYST_TIMER_WAS_ENABLED=0
	BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED=0
	if [ -f /etc/systemd/system/macro-biocatalyst.timer ] && \
		systemctl is-enabled --quiet macro-biocatalyst.timer; then
		BIOCATALYST_TIMER_WAS_ENABLED=1
	fi
	if [ -f /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer ] && \
		systemctl is-enabled --quiet macro-biocatalyst-activation-heartbeat.timer; then
		BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED=1
	fi
	if [ "$BIOCATALYST_RUNTIME_READY" -ne 1 ]; then
		echo "macro-update: refusing BioCatalyst unit update — verified dedicated runtime unavailable" >&2
	elif systemd-analyze verify "$APP_DIR/app/deploy/macro-biocatalyst.service" \
		"$APP_DIR/app/deploy/macro-biocatalyst.timer" \
		"$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" \
		"$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer"; then
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.service" /etc/systemd/system/macro-biocatalyst.service; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst.service" /etc/systemd/system/macro-biocatalyst.service
		fi
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.timer" /etc/systemd/system/macro-biocatalyst.timer; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst.timer" /etc/systemd/system/macro-biocatalyst.timer
		fi
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.service; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.service
		fi
		if ! cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer; then
			install -m 0644 "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer" /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer
		fi
		systemctl daemon-reload
		BIOCATALYST_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: BioCatalyst systemd lane updated without changing its arming state"
		if [ "$BIOCATALYST_TIMER_WAS_ENABLED" -eq 1 ]; then
			systemctl restart macro-biocatalyst.timer
		fi
		if [ "$BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED" -eq 1 ]; then
			systemctl restart macro-biocatalyst-activation-heartbeat.timer
		fi
	else
		echo "macro-update: refusing BioCatalyst unit update — systemd-analyze verify failed" >&2
	fi
fi

# The daemon imports these modules into one persistent interpreter. Config YAML
# is deliberately absent: it is re-read on every 75-second tick and needs no
# restart. Keep the engine/marketing pattern broad because every submodule import
# executes that package's non-inert __init__ first, and the press pipeline reaches
# multiple modules lazily according to the source/item path.
if [ "$PRESS_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(app/deploy/marketing-press-feeds\.service|scripts/marketing_fastlane_daemon\.py|engine/news_translate\.py|engine/marketing/.*\.py|engine/(codex_provider|llm_auth)\.py|engine/codex_lane/runner\.py|lib/(ai_costs|config)\.py)$'; then
	if systemctl is-active --quiet marketing-press-feeds; then
		systemctl restart marketing-press-feeds
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
#   engine/{codex_provider,llm_auth}.py + engine/codex_lane/runner.py
#                          orchestrator_chat Codex fallback + prophet.py
#                          deliberation-spend panel
#   marketing/             marketing.py's outbox approve/reject/decide endpoints →
#                          outbox + rejections. marketing.py's Ad Central panel →
#                          ad_central → ad_allocator, ad_arena, ad_stats. The other
#                          twelve ride the package __init__ (→ state → authority,
#                          charter, claims, cmo, departments, economics, events,
#                          ledgers, opportunity_bus, publication) — confirmed
#                          against a live interpreter's sys.modules. Named, not
#                          globbed: 30 of the 53 marketing modules are nightly-only.
#                          (ad_creative/ad_matrix are NOT here: the panel reads the
#                          creatives ledger, it does not build creatives.)
#   marketing/sentinel     marketing.py's ramp resolver (resolve_ramp) + the
#                          /api/marketing/sentinel panel endpoints — the ramp
#                          caps would deploy dead to the running panel without
#                          a restart (2026-07-28, same class as the outbox gap).
#   scripts/               marketing.py's publish dry-run → marketing_publisher
#                          → copywriter (top-level import: the post-time language
#                          gate banned_language() must fail loudly, so the publisher
#                          imports it at module scope — which puts copywriter in
#                          the panel's load-time closure too).
#   sentinel               marketing.py's caps_by_account (#3884) → resolve_ramp:
#                          the per-account D08 ramp caps shown in the outbox +
#                          publisher payloads import sentinel into the panel.
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
# Admin systemd sandbox: reconcile the reviewed unit before deciding whether to
# restart, so a unit-only hardening/provider change cannot land dead on disk.
ADMIN_UNIT_UPDATED=0
if ! cmp -s "$APP_DIR/admin/deploy/admin.service" /etc/systemd/system/admin.service; then
	if systemd-analyze verify "$APP_DIR/admin/deploy/admin.service"; then
		install -m 0644 "$APP_DIR/admin/deploy/admin.service" /etc/systemd/system/admin.service
		systemctl daemon-reload
		ADMIN_UNIT_UPDATED=1
		RECONCILED=1
		echo "macro-update: admin systemd sandbox updated"
	else
		echo "macro-update: refusing admin unit update — systemd-analyze verify failed" >&2
	fi
fi

# XG-W6 added four that ARE panel imports: labels + learned_rules (the Learning
# panel), health_monitor + blind_identity (the Desk Health panel). Without them
# here, a deploy that changed a halt threshold would leave the admin serving the
# old module out of sys.modules — and the panel that reports whether a desk is
# halted is the last one that should be stale.
#
# XG-W8 adds engine/press/{__init__,desk_planner}.py. The Press panel's cadence
# block now reports the RESOLVED cap (0 while the W2R desk-note lane is dark),
# and it gets that number by calling the planner's own `_triage_cap` rather than
# re-deriving the stricter-of rule — a panel that computes its own answer is a
# panel that can disagree with the engine. That call puts both modules in the
# admin's load-time closure, so without them here a deploy that changed the cap
# resolver would leave the panel serving the old rule out of sys.modules: the
# exact class the outbox gap (2026-07-26) and the four XG-W6 panel modules fixed.
# Only these two — research_triage/research_veto/research_lane are reached solely
# through desk_planner's function-level imports on the PLANNING path, which the
# panel never calls.
#
# The Intelligence Desk approve endpoint adds engine/marketing/{story_lock,
# wire_routing}.py. That endpoint is the ONE admin path that emits a post, and
# both modules are gates on it: wire_routing decides which desk owns the emission
# and story_lock enforces one-owner-per-conversation across desks. Left out here,
# a deploy that retuned the routing table or widened the lock window would leave
# the panel queueing against the OLD rule out of sys.modules — the outbox gap
# (2026-07-26) again, but on the path where being stale means a wrong-desk or
# double-owner post rather than a stale reading.
if [ "$ADMIN_UNIT_UPDATED" -eq 1 ] || echo "$CHANGED" | grep -qE '^(admin/.*|lib/(ai_costs|mastermind_response_log|tiers)\.py|engine/(codex_provider|llm_auth)\.py|engine/codex_lane/runner\.py|engine/neuralweb/(key_pool|ask_brain|support_map|orchestrator_log|trade_memory)\.py|engine/metabolism/(throttle|budget_gate)\.py|engine/marketing/(__init__|accounts|ad_allocator|ad_arena|ad_central|ad_stats|approval_desk|authority|cadence_resolver|charter|claims|cmo|copywriter|departments|economics|events|ledgers|opportunity_bus|outbox|personas|publication|rejections|blind_identity|health_monitor|labels|learned_rules|reply_critics|reply_discovery|reply_drafter|reply_export|reply_producer|reply_queue|reply_voice|rewrite|sentinel|state|story_lock|wire_routing)\.py|engine/press/(__init__|desk_planner)\.py|scripts/marketing_publisher\.py)$'; then
	systemctl is-enabled admin >/dev/null 2>&1 && systemctl restart admin || true
fi

if [ "$REPO_UPDATED" -eq 1 ] || [ "$RECONCILED" -eq 1 ]; then
	echo "macro-update $(date -u +%FT%TZ) ${OLD:0:8}..$(git -C "$APP_DIR" rev-parse --short HEAD)"
fi
