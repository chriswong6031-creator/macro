#!/usr/bin/env bash
# Wire the Mastermind Terminal's data to the macro confluence oracle (EOD, NOT real-time).
# Installs /usr/local/bin/terminal-data — the nightly staging/atomic-swap refresh of the
# full multi-market terminal universe (~8.7k symbols): flagship rebuild + OHLC refresh +
# universe expansion + confluence slices, with flock + shrink-guards so the live manifest
# is never reduced mid-run.
#
# THE WRAPPER BODY IS NOT OURS. It is the charting-app's `ops/terminal-data`, installed
# here VERBATIM from the terminal checkout on the box (/opt/terminal/ops/terminal-data).
# This repo ships no copy of it. Reason — research/GOLDEN_ORACLE_REGIME_BLOCK_FORENSIC_2026-08-10.md
# §5.4, "Deploy last-writer-wins wrapper": TWO installers wrote /usr/local/bin/terminal-data
# and the last one to run won. /opt/terminal/terminal-build.sh reinstalls the charting-app
# copy on EVERY deploy, while this script wrote a vendored macro copy whenever someone ran
# it — so a pass added to only one copy silently disappeared at the next run of the other.
# Measured casualties of exactly that race: the macro rows vanishing from the nightly
# (2026-07-27), the crypto OHLC pass (2026-07-28), and — had this not been fixed — the
# weekly `gen_seasonal_outlook.py` step plus the new `ingest/pull_macro_washout.py` pull
# (charting-app #375), both of which the vendored macro copy never carried.
# There is now exactly ONE wrapper source of truth: the charting-app repo. Any change to
# the nightly goes THERE, and reaches this box through terminal-build.sh.
#
# Deploy model: the charting-app lives on GitHub
# (https://github.com/mastermindx-market-intelligence/mastermind-terminal.git) and deploys are
# git-gated — merge to master, then /opt/terminal/terminal-build.sh on the VPS runs
# `git fetch && git reset --hard origin/master` in /opt/terminal/.gitsrc and
# overlay-syncs the runtime code (ingest/signal_layer/contracts/ops) from that checkout.
# This script installs that wrapper + cron. Requires /opt/terminal/.env with
# POLYGON_API_KEY (transferred out-of-band, never committed).
set -euo pipefail
VENV="/opt/macro/.venv"   # reuse the engine venv (pandas/numpy/pyarrow) + jsonschema for contracts
# The charting-app checkout is the ONE source of the wrapper body (forensic §5.4, header above).
OPS_WRAPPER="${TERMINAL_OPS_WRAPPER:-/opt/terminal/ops/terminal-data}"
log() { echo "[terminal-data] $*"; }

# [1/3] stays macro-side on purpose: the wrapper's interpreter is OUR venv
# (`PY=/opt/macro/.venv/bin/python` inside ops/terminal-data), and its
# `ingest/artifact_conformance` pass needs jsonschema there. Everything else the wrapper
# needs it exports itself (MACRO_REPO, MACRO_STOCKDATA, TERMINAL_MANIFEST), so this script
# has no wrapper env of its own to preserve.
log "[1/3] ensure jsonschema in the engine venv"
"$VENV/bin/pip" install -q jsonschema

log "[2/3] install the nightly refresh wrapper from the charting-app checkout"
if [ ! -f "$OPS_WRAPPER" ]; then
  log "FATAL: $OPS_WRAPPER is missing."
  log "  That file is the ONLY source of /usr/local/bin/terminal-data — this repo deliberately"
  log "  ships no copy of it (forensic §5.4: two copies = last-writer-wins, and the loser's"
  log "  passes vanish silently). Deploy the terminal first (/opt/terminal/terminal-build.sh),"
  log "  then re-run this script. Do NOT hand-write the wrapper: the wrapper cd's to"
  log "  /opt/terminal anyway, so a box without that checkout has nothing for it to drive."
  exit 1
fi
bash -n "$OPS_WRAPPER"   # never install a syntax-broken wrapper
if [ -f /usr/local/bin/terminal-data ] && ! cmp -s "$OPS_WRAPPER" /usr/local/bin/terminal-data; then
  log "live /usr/local/bin/terminal-data differs from $OPS_WRAPPER — replacing it. Diff (live vs source):"
  diff /usr/local/bin/terminal-data "$OPS_WRAPPER" || true
fi
install -m 0755 "$OPS_WRAPPER" /usr/local/bin/terminal-data

log "[3/3] cron: daily 21:30 UTC (after US close; crypto refreshes on weekends too)"
# Low-priority scope: the nightly marathon (~2-4h of gen_slices_all over ~8.7k symbols)
# pegged the droplet's single vCPU at ~99% user, starving Caddy/quote-hub/macro-api of
# scheduling (DO graphs 2026-07-05..12). CPUWeight=10 (vs 100 default) lets live services
# preempt it; MemoryHigh throttles instead of OOM-killing on a memory regression.
# Applied to the live crontab by hand 2026-07-12 — keep this line in sync with it.
{ crontab -l 2>/dev/null | grep -v "terminal-data" || true ; \
  echo "30 21 * * * /usr/bin/systemd-run --scope --quiet -p CPUWeight=10 -p MemoryHigh=1G -p IOWeight=20 /usr/local/bin/terminal-data >> /var/log/terminal-data.log 2>&1" ; } | crontab -

log "DONE — Terminal data refreshes daily; crontab:"; crontab -l | grep terminal-data
