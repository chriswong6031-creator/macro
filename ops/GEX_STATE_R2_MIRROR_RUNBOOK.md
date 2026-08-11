# GEX state R2 mirror

## Boundary

This lane projects the committed nightly files in
`site/options_structure/gex_state/` to
`options_structure/gex_state/` in public R2. It never recomputes GEX, reads
trade-level direction, changes the assumption-signed dealer model, or grants
ranking, scoring, Prophet, sizing, or trading authority. Every root must retain
`authority_tier=display`, `regime_passport.basis=assumption`, and
`regime_passport.verdict=display-only`.

The old M1 `flow-ops-wt` is a dirty, mixed-vintage tree. Its options-matrix job
used to overwrite this prefix with old committed bytes. That inline writer is
retired in `run_options_matrix.sh`; do not reset the shared tree. During rollout
replace only that one runner after proving its exact preimage and that the job
is stopped, retaining a rollback copy.

`com.mastermind.gexstate-mirror` is the sole publication owner. It runs from the
clean standalone clone `/Users/chriswong/gexstate-ops-wt` under one external
publisher lock. Every 15 minutes it reconstructs `_index.json` from every root,
requires semantic equality and the exact prefix key set, then compares every source object
plus the content-hash manifest through authenticated R2 reads. It verifies the public
manifest plus SPY/QQQ/NVDA/index bytes. Any mismatch republishes the complete current set
and retires keys absent from the source.

## Install or refresh on the M1

Use the repo deploy key, a clean clone built beside the final path, and a merge
already proven on `origin/main`. The state directory is external to Git; `.env`
is copied mode 600 and never printed.

```bash
set -euo pipefail
LABEL=com.mastermind.gexstate-mirror
DOMAIN="gui/$(id -u)"
DEPLOY="$HOME/gexstate-ops-wt"
NEW="$DEPLOY.new-$(date -u +%Y%m%dT%H%M%SZ)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
MATRIX_LABEL=com.macro.optionsmatrix
MATRIX_PLIST="$HOME/Library/LaunchAgents/$MATRIX_LABEL.plist"
MATRIX_RUNNER="$HOME/flow-ops-wt/ops/launchd/run_options_matrix.sh"
EXPECTED_MERGE="${EXPECTED_MERGE:?set reviewed merge SHA}"
EXPECTED_MATRIX_PREIMAGE="${EXPECTED_MATRIX_PREIMAGE:?set audited preimage SHA-256}"

test ! -e "$NEW"
git clone --depth 1 --single-branch --branch main \
  --config "core.sshCommand=ssh -i $HOME/.ssh/macro_dashboard_deploy -o IdentitiesOnly=yes" \
  git@github.com:mastermindx-market-intelligence/macro.git "$NEW"
git -C "$NEW" fetch --depth=512 origin main
git -C "$NEW" cat-file -e "$EXPECTED_MERGE^{commit}"
git -C "$NEW" merge-base --is-ancestor "$EXPECTED_MERGE" origin/main
test -z "$(git -C "$NEW" status --porcelain)"
install -m 600 "$HOME/flow-ops-wt/.env" "$NEW/.env"
plutil -lint "$NEW/ops/launchd/$LABEL.plist"
(
  cd "$NEW"
  PYTHONPATH="$NEW" "$HOME/miniconda3/envs/plane/bin/python" \
    -m pytest tests/test_gex_state_index.py -q
)

# Retire the only concurrent writer without refreshing or resetting the dirty
# shared tree. The exact preimage and stopped process are rollout gates.
MATRIX_WAS_LOADED=0
if launchctl print "$DOMAIN/$MATRIX_LABEL" >/dev/null 2>&1; then
  MATRIX_WAS_LOADED=1
  launchctl bootout "$DOMAIN/$MATRIX_LABEL"
fi
! pgrep -f 'scripts[.]build_options_matrix|run_options_matrix[.]sh' >/dev/null
test "$(shasum -a 256 "$MATRIX_RUNNER" | awk '{print $1}')" = \
  "$EXPECTED_MATRIX_PREIMAGE"
MATRIX_BACKUP="$MATRIX_RUNNER.rollback-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$MATRIX_RUNNER" "$MATRIX_BACKUP"
install -m 755 "$NEW/ops/launchd/run_options_matrix.sh" "$MATRIX_RUNNER"
cmp "$NEW/ops/launchd/run_options_matrix.sh" "$MATRIX_RUNNER"
! grep -F 'options_structure/gex_state/' "$MATRIX_RUNNER"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "$DOMAIN/$LABEL"
fi
if [ -e "$DEPLOY" ]; then
  mv "$DEPLOY" "$DEPLOY.rollback-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mv "$NEW" "$DEPLOY"
install -m 644 "$DEPLOY/ops/launchd/$LABEL.plist" "$PLIST"
plutil -lint "$PLIST"
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl print "$DOMAIN/$LABEL" | grep -F "$DEPLOY"
if [ "$MATRIX_WAS_LOADED" -eq 1 ]; then
  launchctl bootstrap "$DOMAIN" "$MATRIX_PLIST"
fi
```

If any step after the matrix-runner replacement fails, restore
`$MATRIX_BACKUP`, unload the new mirror, restore the prior deploy clone/plist,
and re-bootstrap the matrix job before retrying. Never leave both GEX writers
armed and never hand-edit a second path in `flow-ops-wt`.

The first `RunAtLoad` pass must exit 0 and publish (or prove unchanged) with an
exact JSON receipt in `/tmp/gexstate-mirror.stdout.log`. A failed freshness,
authority, index-coverage, R2, or public-byte check exits nonzero; no local
success marker is written.

## Live proof

Require all of the following:

1. the installed clone is clean, on `main`, and its HEAD is the reviewed merge
   or a descendant;
2. launchd points only at `/Users/chriswong/gexstate-ops-wt` and last exit is 0;
3. the matrix runner contains no `options_structure/gex_state/` writer and its
   installed hash matches the reviewed merged blob;
4. the receipt reports the expected settled session, `n_roots`, exact source
   and published object counts, full `direct_verified_count`,
   `public_verified=true`, and required roots SPY/QQQ/NVDA;
5. public `_content_manifest.json` names and hashes every source object, public
   SPY/QQQ/NVDA and `_index.json` match the installed clone, and direct R2 bytes
   match every root; and
6. the three root payloads still say display/assumption/display-only.

Do not use a manual GEX rebuild or backfill as deployment proof. This lane only
publishes already committed settled-session artifacts.
