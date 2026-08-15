#!/bin/bash
set -euo pipefail
umask 027

cache=${1:-/var/cache/mastermind-ci/macro.git}
lock=${2:-/run/lock/mastermind-ci-cache.lock}

exec 9>"$lock"
flock -w 120 9

test -f "$cache/.mastermind-cache-identity.json"
test "$(git --git-dir="$cache" rev-parse --is-bare-repository)" = true

# No prune, repack, or gc belongs in the migration window. The only mutation is an
# atomic main-ref advance plus the objects reachable from it.
git --git-dir="$cache" fetch --no-tags origin \
  +refs/heads/main:refs/heads/main
git --git-dir="$cache" fsck --connectivity-only --no-dangling refs/heads/main
touch "$cache/.last-update-ok"
