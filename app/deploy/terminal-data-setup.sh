#!/usr/bin/env bash
# Wire the Mastermind Terminal's data to the macro confluence oracle (EOD, NOT real-time).
# Installs /usr/local/bin/terminal-data — the nightly staging/atomic-swap refresh of the
# full multi-market terminal universe (~8.7k symbols): flagship rebuild + OHLC refresh +
# universe expansion + confluence slices, with flock + shrink-guards so the live manifest
# is never reduced mid-run. The script itself is VENDORED in this repo as
# app/deploy/terminal-refresh.sh (mirroring how update.sh ships /usr/local/bin/macro-update)
# — edit it THERE, never by hand on the box. An earlier version of this provisioner wrote
# the wrapper from an inline heredoc that had rotted to the original 34-symbol flagship
# builder; re-running it clobbered the evolved live wrapper and silently shrank the
# terminal universe back to ~34-37 symbols. Installing from the vendored file keeps the
# provisioner idempotent against the repo, not against a snapshot frozen in a heredoc.
#
# Deploy model: the charting-app lives on GitHub
# (https://github.com/chriswong6031-creator/mastermind-terminal.git) and deploys are
# git-gated — merge to master, then /opt/terminal/terminal-build.sh on the VPS runs
# `git fetch && git reset --hard origin/master` in /opt/terminal/.gitsrc and
# overlay-syncs the runtime code (ingest/signal_layer/contracts) from that checkout.
# This script installs the wrapper + cron. Requires /opt/terminal/.env with
# POLYGON_API_KEY (transferred out-of-band, never committed).
set -euo pipefail
VENV="/opt/macro/.venv"   # reuse the engine venv (pandas/numpy/pyarrow) + jsonschema for contracts
log() { echo "[terminal-data] $*"; }

log "[1/3] ensure jsonschema in the engine venv"
"$VENV/bin/pip" install -q jsonschema

log "[2/3] install the nightly refresh wrapper from the vendored repo copy"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)/terminal-refresh.sh"
[ -f "$SRC" ] || SRC="/opt/macro/app/deploy/terminal-refresh.sh"   # curl|bash fallback: the checkout
bash -n "$SRC"   # never install a syntax-broken wrapper
if [ -f /usr/local/bin/terminal-data ] && ! cmp -s "$SRC" /usr/local/bin/terminal-data; then
  log "WARN: live /usr/local/bin/terminal-data differs from the repo copy — replacing it. Diff (live vs repo):"
  diff /usr/local/bin/terminal-data "$SRC" || true
fi
install -m 0755 "$SRC" /usr/local/bin/terminal-data

log "[3/3] cron: daily 21:30 UTC (after US close; crypto refreshes on weekends too)"
# Low-priority scope: the nightly marathon (~2-4h of gen_slices_all over ~8.7k symbols)
# pegged the droplet's single vCPU at ~99% user, starving Caddy/quote-hub/macro-api of
# scheduling (DO graphs 2026-07-05..12). CPUWeight=10 (vs 100 default) lets live services
# preempt it; MemoryHigh throttles instead of OOM-killing on a memory regression.
# Applied to the live crontab by hand 2026-07-12 — keep this line in sync with it.
{ crontab -l 2>/dev/null | grep -v "terminal-data" || true ; \
  echo "30 21 * * * /usr/bin/systemd-run --scope --quiet -p CPUWeight=10 -p MemoryHigh=1G -p IOWeight=20 /usr/local/bin/terminal-data >> /var/log/terminal-data.log 2>&1" ; } | crontab -

log "DONE — Terminal data refreshes daily; crontab:"; crontab -l | grep terminal-data
