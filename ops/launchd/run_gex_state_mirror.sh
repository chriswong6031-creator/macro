#!/bin/sh
# Fast-forward the dedicated M1 projection clone and publish committed GEX state.
set -eu

REPO="${GEX_STATE_DEPLOY_REPO:-/Users/chriswong/gexstate-ops-wt}"
PYTHON="${GEX_STATE_PYTHON:-/Users/chriswong/miniconda3/envs/plane/bin/python}"
STATE_DIR="${GEX_STATE_MIRROR_STATE_DIR:-/Users/chriswong/Library/Application Support/Mastermind/gexstate-mirror}"
PUBLIC_BASE="${GEX_STATE_PUBLIC_BASE:-https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev}"

test -d "$REPO/.git"
test "$(git -C "$REPO" symbolic-ref --short HEAD)" = "main"
git -C "$REPO" diff --quiet
git -C "$REPO" diff --cached --quiet

# Bounded retry closes the small fetch/ls-remote race without resetting a dirty
# tree. A non-fast-forward or local modification is a hard stop.
attempt=1
while [ "$attempt" -le 3 ]; do
    git -C "$REPO" fetch --depth=512 origin main
    git -C "$REPO" merge --ff-only origin/main
    LOCAL_MAIN=$(git -C "$REPO" rev-parse HEAD)
    REMOTE_MAIN=$(git -C "$REPO" ls-remote origin refs/heads/main | awk '{print $1}')
    if [ -n "$REMOTE_MAIN" ] && [ "$LOCAL_MAIN" = "$REMOTE_MAIN" ]; then
        break
    fi
    attempt=$((attempt + 1))
done
test -n "${REMOTE_MAIN:-}"
test "$LOCAL_MAIN" = "$REMOTE_MAIN"
git -C "$REPO" merge-base --is-ancestor "$LOCAL_MAIN" origin/main

mkdir -p "$STATE_DIR"
cd "$REPO"
GEX_STATE_SOURCE_COMMIT="$LOCAL_MAIN" \
PYTHONPATH="$REPO" \
"$PYTHON" -m scripts.mirror_gex_state_r2 \
    --require-expected-session \
    --required-root SPY \
    --required-root QQQ \
    --required-root NVDA \
    --public-base "$PUBLIC_BASE" \
    --state-file "$STATE_DIR/state.json"
