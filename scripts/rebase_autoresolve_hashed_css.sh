#!/usr/bin/env bash
# Finish a `git pull --rebase` that stopped ONLY on rename/rename (or rename/delete)
# conflicts among content-hashed derived assets under site/assets/css/ and
# site/assets/js/ (both minted by scripts/externalize_css.py from inline <style> /
# <script data-externalize> blocks; filename == sha256(content)[:8]; the script
# name predates the js tree).
#
# Why: concurrent render lanes re-externalize the same inline block after
# divergent re-renders, so each side renames site/assets/<tree>/<old> to a DIFFERENT
# new hash. `-X theirs` only settles content-level conflicts — a rename/rename path
# conflict stops the rebase identically on every retry, and the push loops used to
# give up after 5 attempts with a green run (2026-07-22 asia-close run 29904079071:
# the whole day's engine outputs dropped; data/hk_regime stuck at 07-21 and fed the
# false "HK data STALE" banner).
#
# Resolution: KEEP BOTH sides' hashed files. Each page links exactly one hash, so
# keeping both guarantees no dangling <link> regardless of which side's HTML survived
# `-X theirs`; the next externalize_css run prunes whichever hash ends up unreferenced.
# Each kept file is restored BYTE-PURE from its own commit (HEAD / REBASE_HEAD) — git
# content-merges the renamed pair and would otherwise stage the merged blob under both
# names, breaking the filename==hash contract that the `?v=<hash>` immutable-cache rule
# relies on. A source path renamed away on both sides is dropped from the index.
#
# Exit 0: rebase completed — caller proceeds to push.
# Exit 1: no rebase in progress, or unmerged paths outside the derived hashed-asset
#         scope — the rebase (if any) is left in place so the caller's existing
#         `git rebase --abort` + retry/fail path is unchanged. Never aborts itself.
set -u

# Strictly the two content-hashed trees (hex filename, extension matching its
# tree) — a real, hand-authored asset must never be auto-resolved here.
ALLOW_RE='^site/assets/(css/[0-9a-f]{6,64}\.css|js/[0-9a-f]{6,64}\.js)$'

gitdir=$(git rev-parse --git-dir 2>/dev/null) || exit 1
in_rebase() { [ -d "$gitdir/rebase-merge" ] || [ -d "$gitdir/rebase-apply" ]; }

in_rebase || { echo "autoresolve_hashed_css: no rebase in progress"; exit 1; }

# One pass per replayed commit that stops (engine commit + render-heal follow-ups);
# the bound is a runaway backstop, not a real limit.
for _pass in 1 2 3 4 5 6 7 8 9 10; do
  unmerged=$(git ls-files -u | cut -f2 | LC_ALL=C sort -u)
  if [ -n "$unmerged" ]; then
    bad=$(printf '%s\n' "$unmerged" | grep -Ev "$ALLOW_RE" || true)
    if [ -n "$bad" ]; then
      echo "autoresolve_hashed_css: refusing — unmerged paths outside the hashed site/assets/{css,js} trees:"
      printf '%s\n' "$bad" | sed 's/^/  /'
      exit 1
    fi
    git rev-parse -q --verify REBASE_HEAD >/dev/null \
      || { echo "autoresolve_hashed_css: REBASE_HEAD unavailable"; exit 1; }
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      stages=$(git ls-files -u -- "$p" | awk '{print $3}')
      if printf '%s\n' "$stages" | grep -qx 3; then
        git restore --source=REBASE_HEAD --staged --worktree -- "$p" || exit 1
        echo "autoresolve_hashed_css: kept $p (replayed side, byte-pure from REBASE_HEAD)"
      elif printf '%s\n' "$stages" | grep -qx 2; then
        git restore --source=HEAD --staged --worktree -- "$p" || exit 1
        echo "autoresolve_hashed_css: kept $p (upstream side, byte-pure from HEAD)"
      else
        git rm -q -f -- "$p" || exit 1
        echo "autoresolve_hashed_css: dropped $p (source renamed away on both sides)"
      fi
    done <<EOF
$unmerged
EOF
  fi
  if GIT_EDITOR=true git rebase --continue; then
    in_rebase || { echo "autoresolve_hashed_css: rebase completed"; exit 0; }
    continue
  fi
  in_rebase || exit 1
  # --continue refused with nothing left to resolve or commit: the replayed commit
  # came out empty (both sides landed the identical change) — skip it and keep going.
  if [ -z "$(git ls-files -u)" ] && git diff --cached --quiet; then
    git rebase --skip || exit 1
    in_rebase || { echo "autoresolve_hashed_css: rebase completed (empty commit skipped)"; exit 0; }
  fi
done
echo "autoresolve_hashed_css: pass bound exhausted"
exit 1
