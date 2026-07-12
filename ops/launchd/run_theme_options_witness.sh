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
# SHARED WORKTREE CONTRACT (flow-ops-wt)
# ─────────────────────────────────────────────────────────────────────────────
# flow-ops-wt is shared with the mastermind lanes (optionshub 16:45 ET,
# liveflow RTH poller, flowenrich). This lane fires 17:15 ET, after the RTH
# lanes self-exit. HEAD is DETACHED at an origin/main commit by convention —
# this script never creates or switches branches: it commits on the detached
# HEAD, rebases onto origin/main (--autostash parks runtime-dirty tracked
# files such as data/run_status.json), and pushes HEAD:main. On any failure
# the rebase is aborted; the worktree is never left mid-rebase. A conflicted
# autostash pop (rebase still exits 0!) is detected and hard-reset so sibling
# lanes never see conflict markers or a stray stash entry.
#
# Side effect BY DESIGN: each successful run advances the detached HEAD to
# fresh origin/main + this commit — which keeps flow-ops-wt near origin/main,
# as the plist header requires. A push failure is non-destructive: the commit
# stays local and the NEXT run's rebase carries it forward.
#
# RACE HANDLING mirrors the daily.yml "commit data" step:
#   fetch → collision sweep (a local non-ignored untracked file that is now
#   TRACKED on origin/main would abort the rebase checkout identically on
#   every retry; origin/main is authoritative for anything it tracks, and
#   everything this lane publishes is already committed above — so delete the
#   local copy and let the rebase materialize main's version) →
#   rebase --autostash -X theirs (in a rebase "theirs" = the commit being
#   replayed, i.e. OUR fresh legs win any artifact conflict with the runner's
#   null write) → push, retry ×5 with backoff.
#   Deviation from daily.yml: explicit fetch+rebase instead of `git pull
#   --rebase` because HEAD is detached (pull requires a branch).
#
# LOG TAILING:
#   tail -f /tmp/theme_options_witness.stdout.log /tmp/theme_options_witness.stderr.log
#
# MANUAL RUN (smoke, commits+pushes for real — use a throwaway --date only if
# you intend to publish it):
#   /Users/chriswong/flow-ops-wt/ops/launchd/run_with_env.sh \
#     /Users/chriswong/flow-ops-wt/.env \
#     /Users/chriswong/flow-ops-wt/ops/launchd/run_theme_options_witness.sh

set -u

REPO="/Users/chriswong/flow-ops-wt"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
ART_NW="data/neuralweb/theme_options_witness.json"
ART_SITE="site/basketdata/options_witness.json"

cd "$REPO" || { echo "[theme_options_witness] ERROR: cannot cd $REPO"; exit 1; }

# Dead-worktree guard: if the worktree's .git link no longer resolves, git
# commands fall through to whatever repo encloses the path. Refuse to run
# rather than commit into the wrong tree.
TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [ "$TOPLEVEL" != "$REPO" ]; then
    echo "[theme_options_witness] ERROR: git toplevel '$TOPLEVEL' != $REPO — dead worktree? aborting"
    exit 1
fi

echo "[theme_options_witness] running engine (THETADATA_STORE=${THETADATA_STORE:-unset})"
if ! "$PYTHON" -m engine.theme_options_witness; then
    echo "[theme_options_witness] ERROR: engine run failed — not committing"
    exit 1
fi

# ── commit tail ──────────────────────────────────────────────────────────────
# Narrow add: exactly the two artifacts this lane owns. The pathspec-limited
# commit below also insulates us from anything another lane left staged.
git add -- "$ART_NW" "$ART_SITE"
if git diff --cached --quiet -- "$ART_NW" "$ART_SITE"; then
    echo "[theme_options_witness] no artifact changes — nothing to commit"
    exit 0
fi

git -c user.name="dashboard-bot" -c user.email="actions@users.noreply.github.com" \
    commit -m "data: theme options witness $(date -u +%F)" -- "$ART_NW" "$ART_SITE"

n=1
while [ "$n" -le 5 ]; do
    git fetch origin main || true

    # Collision sweep (see RACE HANDLING above). /bin/sh has no process
    # substitution — stage the two sorted lists in temp files.
    UNTRACKED_LIST=$(mktemp) || exit 1
    TRACKED_LIST=$(mktemp) || exit 1
    git ls-files --others --exclude-standard | LC_ALL=C sort > "$UNTRACKED_LIST"
    git ls-tree -r --name-only origin/main | LC_ALL=C sort > "$TRACKED_LIST"
    comm -12 "$UNTRACKED_LIST" "$TRACKED_LIST" | while IFS= read -r f; do
        rm -f -- "$f" || true
    done
    rm -f "$UNTRACKED_LIST" "$TRACKED_LIST"

    if git rebase --autostash -X theirs origin/main; then
        # `git rebase --autostash` exits 0 even when re-applying the autostash
        # CONFLICTS (the rebase succeeded; only the pop failed) — leaving
        # conflict markers plus a leftover stash that would poison the sibling
        # lanes sharing this worktree. Detect via unmerged index entries and
        # reset: the stashed content is runtime state (e.g. data/run_status.json)
        # that its owner lane regenerates on its next run.
        if [ -n "$(git ls-files -u 2>/dev/null)" ]; then
            echo "[theme_options_witness] autostash pop conflicted — hard-resetting working tree (runtime files regenerate)"
            git reset --hard HEAD
            if git stash list | sed -n 1p | grep -q autostash; then
                git stash drop >/dev/null 2>&1 || true
            fi
        fi
        if git push origin HEAD:refs/heads/main; then
            echo "[theme_options_witness] pushed artifacts on attempt $n"
            exit 0
        fi
    fi
    git rebase --abort 2>/dev/null || true
    echo "[theme_options_witness] push attempt $n lost a race; re-syncing"
    sleep $((n * 7))
    n=$((n + 1))
done

echo "[theme_options_witness] ERROR: could not push after 5 attempts — commit stays local; next run's rebase carries it forward"
exit 1
