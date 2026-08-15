#!/bin/bash
set -euo pipefail
umask 027

cache=${1:-/var/cache/mastermind-ci/macro.git}
lock=${2:-/run/lock/mastermind-ci-cache.lock}

exec 9>"$lock"
flock -w 120 9

test -f "$cache/.mastermind-cache-identity.json"
test "$(git --git-dir="$cache" rev-parse --is-bare-repository)" = true
git --git-dir="$cache" config gc.auto 0
git --git-dir="$cache" config maintenance.auto false

# No prune, repack, or gc belongs in the migration window. The only mutation is an
# atomic main-ref advance plus the objects reachable from it.
git --git-dir="$cache" fetch --no-auto-maintenance --no-tags origin \
  +refs/heads/main:refs/heads/main

# The peer seed is intentionally shallow at the audited bootstrap commit. Its
# unreachable object estate may contain inert fragments from the M2's historical
# partial clone, so whole-object-store fsck would judge objects CI cannot reach.
# Validate every object reachable from the maintained shallow main ref instead.
missing=$(
  git --git-dir="$cache" rev-list --objects --no-object-names refs/heads/main |
    GIT_NO_LAZY_FETCH=1 git --git-dir="$cache" cat-file --batch-check |
    awk '$2 == "missing" {count += 1} END {print count + 0}'
)
test "$missing" -eq 0
touch "$cache/.last-update-ok"
