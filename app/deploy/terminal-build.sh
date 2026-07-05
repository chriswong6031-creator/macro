#!/usr/bin/env bash
# Zero-downtime build for the Mastermind Terminal (Next.js).
#
# Builds into an isolated staging tree and atomically swaps `.next` ONLY after
# the build is verified complete (BUILD_ID present). A failed or in-progress
# build can therefore NEVER take the live site down — the running server keeps
# serving the previous `.next` until the instant of the atomic swap.
#
# History: 2026-07-05 the old in-place `next build` wiped `.next` under the live
# server; a restart mid-build crash-looped ("next: not found") and 502'd the
# site for ~13 min. This script removes that failure mode.
set -euo pipefail

APP=/opt/terminal/terminal
cd "$APP"
log(){ echo "[build] $*"; }

log "node $(node -v)"

# 1) deps — refresh only when the lockfile actually changed, so a routine deploy
#    doesn't churn the running server's node_modules.
if [ ! -d node_modules ] || [ package-lock.json -nt node_modules/.package-lock.json ]; then
  log "installing deps (npm ci, fallback install)"
  npm ci || npm install
else
  log "deps unchanged — skipping npm ci"
fi

# 2) stage: hardlinked copy of the source (near-free, same filesystem) that
#    shares node_modules via symlink. Live .next is excluded and untouched.
STAGE=$(mktemp -d "$(dirname "$APP")/.stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
log "staging in $STAGE"
rsync -a --delete \
  --exclude='.next' --exclude='.next.bak' --exclude='.next.broken' --exclude='.stage.*' \
  --exclude='node_modules' \
  --link-dest="$APP/" "$APP/" "$STAGE/"
ln -s "$APP/node_modules" "$STAGE/node_modules"

# 3) build into the staging tree — the slow part; live site stays up throughout.
log "next build (staging) …"
( cd "$STAGE" && npm run build )

# 4) verify the new build is complete before touching anything live.
if [ ! -f "$STAGE/.next/BUILD_ID" ]; then
  log "BUILD FAILED (no BUILD_ID) — live site untouched, aborting"
  exit 1
fi
log "new build OK: BUILD_ID=$(cat "$STAGE/.next/BUILD_ID")"

# 5) atomic swap (rename within one filesystem is atomic).
rm -rf "$APP/.next.bak"
[ -d "$APP/.next" ] && mv "$APP/.next" "$APP/.next.bak"
mv "$STAGE/.next" "$APP/.next"
log "swapped .next (previous build kept as .next.bak)"

# 6) restart onto the complete build; auto-rollback if it doesn't come up.
systemctl restart terminal
sleep 6
if curl -fsS http://127.0.0.1:3000/ -o /dev/null -w "[build] localhost:3000 -> %{http_code}\n"; then
  log "DONE — live and healthy"
else
  log "post-restart health check FAILED — rolling back to previous .next.bak"
  if [ -d "$APP/.next.bak" ]; then
    rm -rf "$APP/.next.broken"
    mv "$APP/.next" "$APP/.next.broken"
    mv "$APP/.next.bak" "$APP/.next"
    systemctl restart terminal
    log "rolled back to previous build"
  fi
  exit 1
fi
