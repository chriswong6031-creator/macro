#!/bin/sh
# ops/launchd/run_theme_options_witness.sh
#
# Runner for the TIL W11 theme options witness (engine.theme_options_witness)
# plus a git commit+push tail. Invoked by com.macro.theme-options-witness.plist
# via run_with_env.sh (which sources .env → THETADATA_STORE, so the engine
# reads the real ThetaData EOD store instead of emitting the honest null).
#
# WHY A COMMIT TAIL
# ─────────────────────────────────────────────────────────────────────────────
# The two artifacts are git-tracked, but this lane is the ONLY writer that has
# the ThetaData store, and it runs in a host worktree no nightly runner can
# see. Without a push the real legs never reach git — the daily.yml collect
# step keeps serving the honest null forever (the state TIL W11 was stuck in
# from its 2026-07-09 merge until this wrapper existed). The engine side of
# the coexistence is the keep-last-real law in engine/theme_options_witness.py:
# a store-less run skips its null write while the committed artifact holds
# real legs newer than 6 days.
#
# TCC LAW — WHY THE PUSH HAPPENS IN A SEPARATE $HOME REPO
# ─────────────────────────────────────────────────────────────────────────────
# launchd agents are DENIED all reads under ~/Documents (macOS TCC). The
# flow-ops-wt worktree's FILES live under $HOME, so the engine runs fine —
# but its gitdir is ~/Documents/.../.git/worktrees/flow-ops-wt, so EVERY git
# command inside flow-ops-wt fails under launchd (empirically: rev-parse
# returns empty; first kickstart 2026-07-12 died on the dead-worktree guard).
# Therefore the commit+push tail runs in $PUSH_REPO: a small STANDALONE
# sparse blob-less clone (own .git under $HOME, only data/neuralweb +
# site/basketdata checked out, ~100MB). The wrapper self-heals it if absent.
# The repo is disposable — delete it and the next run re-clones.
#
# Consequence: this lane no longer advances flow-ops-wt (no git ops there).
# Keeping flow-ops-wt's ENGINE CODE near origin/main is an operator/ops
# concern: run `git -C /Users/chriswong/flow-ops-wt fetch origin && git -C
# /Users/chriswong/flow-ops-wt checkout --detach origin/main` from a normal
# (non-launchd) shell occasionally, and after any engine change.
#
# RACE HANDLING (simpler than the daily.yml rebase dance — the push repo is
# single-purpose, so there is nothing local to preserve):
#   fetch --depth 1 → reset --hard origin/main (also self-heals any debris
#   from a previous failed run) → copy the two artifacts in → narrow commit →
#   push; on a lost race, retry ×5 with backoff, re-syncing each time.
#
# SMOKE-TESTING THE TAIL ALONE (skips the ~5 min engine run; uses whatever
# artifacts are already in flow-ops-wt):
#   WITNESS_SKIP_ENGINE=1 /Users/chriswong/flow-ops-wt/ops/launchd/run_with_env.sh \
#     /Users/chriswong/flow-ops-wt/.env \
#     /Users/chriswong/flow-ops-wt/ops/launchd/run_theme_options_witness.sh
#
# LOG TAILING:
#   tail -f /tmp/theme_options_witness.stdout.log /tmp/theme_options_witness.stderr.log

set -u

REPO="/Users/chriswong/flow-ops-wt"
PUSH_REPO="/Users/chriswong/witness-push-repo"
REMOTE_URL="https://github.com/chriswong6031-creator/macro.git"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
ART_NW="data/neuralweb/theme_options_witness.json"
ART_SITE="site/basketdata/options_witness.json"

cd "$REPO" || { echo "[theme_options_witness] ERROR: cannot cd $REPO"; exit 1; }

# ── engine (file reads/writes only — no git; flow-ops-wt gitdir is TCC-dead) ──
if [ "${WITNESS_SKIP_ENGINE:-0}" = "1" ]; then
    echo "[theme_options_witness] WITNESS_SKIP_ENGINE=1 — skipping engine, pushing existing artifacts"
else
    echo "[theme_options_witness] running engine (THETADATA_STORE=${THETADATA_STORE:-unset})"
    if ! "$PYTHON" -m engine.theme_options_witness; then
        echo "[theme_options_witness] ERROR: engine run failed — not committing"
        exit 1
    fi
fi

if [ ! -f "$REPO/$ART_NW" ] || [ ! -f "$REPO/$ART_SITE" ]; then
    echo "[theme_options_witness] ERROR: artifact(s) missing in $REPO — nothing to push"
    exit 1
fi

# ── commit tail (in the $HOME push repo — see TCC LAW above) ─────────────────
if [ ! -d "$PUSH_REPO/.git" ]; then
    echo "[theme_options_witness] push repo absent — cloning (sparse, blob-less, depth 1)"
    git clone --depth 1 --filter=blob:none --sparse "$REMOTE_URL" "$PUSH_REPO" \
        || { echo "[theme_options_witness] ERROR: clone failed"; exit 1; }
    git -C "$PUSH_REPO" sparse-checkout set data/neuralweb site/basketdata \
        || { echo "[theme_options_witness] ERROR: sparse-checkout failed"; exit 1; }
fi

cd "$PUSH_REPO" || { echo "[theme_options_witness] ERROR: cannot cd $PUSH_REPO"; exit 1; }

# Standalone-repo guard: gitdir must resolve INSIDE the push repo. A gitdir
# anywhere else (worktree layout, or fall-through to an enclosing repo) would
# reintroduce the TCC failure or commit into the wrong tree.
TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
GITDIR=$(git rev-parse --absolute-git-dir 2>/dev/null || echo "")
if [ "$TOPLEVEL" != "$PUSH_REPO" ] || [ "$GITDIR" != "$PUSH_REPO/.git" ]; then
    echo "[theme_options_witness] ERROR: push repo layout wrong (toplevel='$TOPLEVEL' gitdir='$GITDIR') — aborting"
    exit 1
fi

n=1
while [ "$n" -le 5 ]; do
    if git fetch --depth 1 origin main \
        && git reset --hard refs/remotes/origin/main >/dev/null; then
        cp "$REPO/$ART_NW" "$ART_NW" || exit 1
        cp "$REPO/$ART_SITE" "$ART_SITE" || exit 1
        git add -- "$ART_NW" "$ART_SITE"
        if git diff --cached --quiet -- "$ART_NW" "$ART_SITE"; then
            echo "[theme_options_witness] artifacts identical to origin/main — nothing to push"
            exit 0
        fi
        if git -c user.name="dashboard-bot" -c user.email="actions@users.noreply.github.com" \
                commit -q -m "data: theme options witness $(date -u +%F)" -- "$ART_NW" "$ART_SITE" \
            && git push origin main; then
            echo "[theme_options_witness] pushed artifacts on attempt $n"
            exit 0
        fi
    fi
    echo "[theme_options_witness] push attempt $n lost a race / failed; re-syncing"
    sleep $((n * 7))
    n=$((n + 1))
done

echo "[theme_options_witness] ERROR: could not push after 5 attempts — artifacts remain in $REPO; next run retries"
exit 1
