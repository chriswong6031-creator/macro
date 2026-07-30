#!/bin/sh
# ops/launchd/run_index_gex_history.sh
#
# Runner for the OIP E3c weekly index dealer-gamma HISTORY reconstruction
# (scripts.build_index_gex_history) plus an R2 offsite sync and a git commit+push
# tail. Invoked by com.macro.indexgexhistory.plist via run_with_env.sh (which
# sources .env → THETADATA_STORE, so the resolver finds the real ThetaData EOD
# store instead of exiting with the honest "did not resolve" message).
#
# WHY THIS LANE EXISTS
# ─────────────────────────────────────────────────────────────────────────────
# The reconstruction joins the ThetaData greeks ⋈ oi stores (2017→, ~60 GB) and
# that store exists ONLY on this host. It was originally run BY HAND, once, in
# 2026-06 (#1374) — and then never again: the committed parquets froze at
# 2026-07-02 while engine/market_gamma kept computing percentiles off the stale
# distribution with nothing in the artifact saying how old it was. This lane is
# the fix on the ops side; engine/market_gamma's window/staleness disclosure is
# the fix on the honesty side.
#
# CI AND THE NIGHTLY NEVER TOUCH THE THETA STORE. They read the committed
# data/index_gex_history/*.parquet (and its R2 mirror). That invariant is why
# this job has to push: without the push the rebuild never reaches any consumer.
#
# WHY A COMMIT TAIL, AND WHY IN A SEPARATE $HOME REPO (TCC LAW)
# ─────────────────────────────────────────────────────────────────────────────
# Identical to ops/launchd/run_theme_options_witness.sh — read that header for
# the full reasoning. Short version: launchd agents are DENIED all reads under
# ~/Documents (macOS TCC). flow-ops-wt's FILES live under $HOME so the engine
# runs fine, but its gitdir is ~/Documents/.../.git/worktrees/flow-ops-wt, so
# every git command inside it fails under launchd. The commit+push tail therefore
# runs in $PUSH_REPO: a small STANDALONE sparse blob-less clone (own .git under
# $HOME, only data/index_gex_history checked out). Its own push repo, separate
# from the witness lane's, so the two never fight over the sparse-checkout set.
# The repo is disposable — delete it and the next run re-clones.
#
# ARTIFACTS PUSHED (5 files, ~850 KB total):
#   data/index_gex_history/SPY.parquet
#   data/index_gex_history/QQQ.parquet
#   data/index_gex_history/IWM.parquet
#   data/index_gex_history/DIA.parquet
#   data/index_gex_history/_manifest.json
#
# R2 OFFSITE: python -m scripts.publish_r2 --dirs index_gex_history --no-manifest
# runs BEFORE the push (the parquets are already on disk by then and the sync is
# a seconds-long md5 delta). --no-manifest because this is a partial-tree
# invocation — see the publish_r2 module docstring.
#
# SMOKE-TESTING THE TAIL ALONE (skips the ~20 min rebuild; pushes whatever
# parquets are already in flow-ops-wt):
#   INDEXGEX_SKIP_ENGINE=1 /Users/chriswong/flow-ops-wt/ops/launchd/run_with_env.sh \
#     /Users/chriswong/flow-ops-wt/.env \
#     /Users/chriswong/flow-ops-wt/ops/launchd/run_index_gex_history.sh
#
# LOG TAILING:
#   tail -f /tmp/index_gex_history.stdout.log /tmp/index_gex_history.stderr.log

set -u

REPO="/Users/chriswong/flow-ops-wt"
PUSH_REPO="/Users/chriswong/indexgex-push-repo"
REMOTE_URL="https://github.com/chriswong6031-creator/macro.git"
PYTHON="/opt/homebrew/Caskroom/miniconda/base/bin/python"
ART_DIR="data/index_gex_history"

cd "$REPO" || { echo "[index_gex_history] ERROR: cannot cd $REPO"; exit 1; }

# ── reconstruction (file reads/writes only — no git; flow-ops-wt gitdir is TCC-dead) ──
if [ "${INDEXGEX_SKIP_ENGINE:-0}" = "1" ]; then
    echo "[index_gex_history] INDEXGEX_SKIP_ENGINE=1 — skipping rebuild, pushing existing parquets"
else
    echo "[index_gex_history] rebuilding (THETADATA_STORE=${THETADATA_STORE:-unset})"
    if ! "$PYTHON" -m scripts.build_index_gex_history; then
        echo "[index_gex_history] ERROR: rebuild failed — not committing"
        exit 1
    fi
fi

# ── completeness gate ────────────────────────────────────────────────────────
# File EXISTENCE is NOT the gate. The parquets are git-tracked, so all four are on disk
# from the checkout even when this run wrote none of them — an existence check would
# happily push a stale or partially-refreshed store as if it were a fresh rebuild. The
# gate is the manifest's roots_read from THIS run: build_index_gex_history records a root
# there only after it actually wrote that root's parquet, and the shrink guard
# deliberately omits a refused root. Also fails when the run refused any root.
if [ "${INDEXGEX_SKIP_ENGINE:-0}" != "1" ]; then
    if ! "$PYTHON" - "$REPO/$ART_DIR/_manifest.json" <<'PYGATE'
import json, sys
required = {"SPY", "QQQ", "IWM", "DIA"}
try:
    m = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"[index_gex_history] ERROR: manifest unreadable: {e}")
    raise SystemExit(1)
read = {r for r, yrs in (m.get("roots_read") or {}).items() if yrs}
refused = m.get("roots_refused_shrink") or {}
missing = sorted(required - read)
if missing:
    print(f"[index_gex_history] ERROR: this run wrote no rows for {missing} "
          f"(roots_read={sorted(read)}) — partial rebuild, nothing to push")
    raise SystemExit(1)
if refused:
    print(f"[index_gex_history] ERROR: shrink guard refused {sorted(refused)} "
          f"— {refused} — nothing to push")
    raise SystemExit(1)
print(f"[index_gex_history] manifest gate OK: roots_read={sorted(read)}")
PYGATE
    then
        exit 1
    fi
fi

# The files must also be present on disk (a torn write, a cleaned worktree).
for f in SPY.parquet QQQ.parquet IWM.parquet DIA.parquet _manifest.json; do
    if [ ! -f "$REPO/$ART_DIR/$f" ]; then
        echo "[index_gex_history] ERROR: $ART_DIR/$f missing in $REPO — nothing to push"
        exit 1
    fi
done

# ── R2 offsite sync (best effort — a failure here must not block the push) ────
echo "[index_gex_history] syncing offsite copy to R2"
if ! "$PYTHON" -m scripts.publish_r2 --dirs index_gex_history --no-manifest; then
    echo "[index_gex_history] WARNING: R2 sync failed — continuing to the git push"
fi

# ── commit tail (in the $HOME push repo — see TCC LAW above) ─────────────────
if [ ! -d "$PUSH_REPO/.git" ]; then
    echo "[index_gex_history] push repo absent — cloning (sparse, blob-less, depth 1)"
    git clone --depth 1 --filter=blob:none --sparse "$REMOTE_URL" "$PUSH_REPO" \
        || { echo "[index_gex_history] ERROR: clone failed"; exit 1; }
    git -C "$PUSH_REPO" sparse-checkout set "$ART_DIR" \
        || { echo "[index_gex_history] ERROR: sparse-checkout failed"; exit 1; }
fi

cd "$PUSH_REPO" || { echo "[index_gex_history] ERROR: cannot cd $PUSH_REPO"; exit 1; }

# Standalone-repo guard: gitdir must resolve INSIDE the push repo. A gitdir anywhere
# else (worktree layout, or fall-through to an enclosing repo) would reintroduce the
# TCC failure or commit into the wrong tree.
TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
GITDIR=$(git rev-parse --absolute-git-dir 2>/dev/null || echo "")
if [ "$TOPLEVEL" != "$PUSH_REPO" ] || [ "$GITDIR" != "$PUSH_REPO/.git" ]; then
    echo "[index_gex_history] ERROR: push repo layout wrong (toplevel='$TOPLEVEL' gitdir='$GITDIR') — aborting"
    exit 1
fi

n=1
while [ "$n" -le 5 ]; do
    if git fetch --depth 1 origin main \
        && git reset --hard refs/remotes/origin/main >/dev/null; then
        mkdir -p "$ART_DIR" || exit 1
        for f in SPY.parquet QQQ.parquet IWM.parquet DIA.parquet _manifest.json; do
            cp "$REPO/$ART_DIR/$f" "$ART_DIR/$f" || exit 1
        done
        git add -- "$ART_DIR"
        if git diff --cached --quiet -- "$ART_DIR"; then
            echo "[index_gex_history] parquets identical to origin/main — nothing to push"
            exit 0
        fi
        if git -c user.name="dashboard-bot" -c user.email="actions@users.noreply.github.com" \
                commit -q -m "data: index dealer-gamma history rebuild $(date -u +%F)" -- "$ART_DIR" \
            && git push origin main; then
            echo "[index_gex_history] pushed parquets on attempt $n"
            exit 0
        fi
    fi
    echo "[index_gex_history] push attempt $n lost a race / failed; re-syncing"
    sleep $((n * 7))
    n=$((n + 1))
done

echo "[index_gex_history] ERROR: could not push after 5 attempts — parquets remain in $REPO; next run retries"
exit 1
