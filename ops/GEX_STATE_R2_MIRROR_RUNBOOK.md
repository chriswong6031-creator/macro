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
can still overwrite this prefix with old committed bytes. Do not reset or edit
that shared tree. `com.mastermind.gexstate-mirror` therefore runs from the clean
standalone clone `/Users/chriswong/gexstate-ops-wt`, compares SPY/QQQ/NVDA plus
`_index.json` byte-for-byte against public R2 every 15 minutes, and republishes
the complete current set whenever either the committed manifest or a public
anchor differs.

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
EXPECTED_MERGE="${EXPECTED_MERGE:?set reviewed merge SHA}"

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
```

The first `RunAtLoad` pass must exit 0 and publish (or prove unchanged) with an
exact JSON receipt in `/tmp/gexstate-mirror.stdout.log`. A failed freshness,
authority, index-coverage, R2, or public-byte check exits nonzero; no local
success marker is written.

## Live proof

Require all of the following:

1. the installed clone is clean, on `main`, and its HEAD is the reviewed merge
   or a descendant;
2. launchd points only at `/Users/chriswong/gexstate-ops-wt` and last exit is 0;
3. the receipt reports the expected settled session, `n_roots`, exact object
   count, `public_verified=true`, and required roots SPY/QQQ/NVDA;
4. public SPY/QQQ/NVDA and `_index.json` bytes match the installed clone; and
5. the three root payloads still say display/assumption/display-only.

Do not use a manual GEX rebuild or backfill as deployment proof. This lane only
publishes already committed settled-session artifacts.
