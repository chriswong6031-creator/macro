#!/bin/bash
# strip_conflict_markers.sh — refuse to stage stash/rebase wreckage.
#
# 2026-08-01 incident: inside a push-retry loop, `git pull --rebase --autostash`
# hit a conflicted autostash apply, which wrote literal git conflict-marker
# lines (opener label "Updated upstream", closer label "Stashed changes") into
# tracked site/ pages; the next broad `git add site/ templates/` staged them
# verbatim and d29e4dd44d + ffed202405d shipped the wreckage across 1,704
# committed pages — served live by the VPS's 3-min pull until c1bfee482a
# healed them. The autostash parks THROWAWAY working-tree writes (render
# scratch, engine data caches), so a conflicted apply is never content worth
# publishing: the correct committed state is HEAD, always.
#
# Run this immediately BEFORE any broad `git add` of rendered/derived trees
# (site/, templates/, data/, reports/): every file DIRTY vs HEAD that carries
# both a column-0 conflict opener and closer is restored from HEAD instead of
# being staged. Optional args override the default sweep pathspecs.
#
# Bash 3.2-compatible (macOS lane runners) and GNU-compatible (CI replay job).
# Never fails the calling lane: exit 0 always.
set -uo pipefail

sweep=("$@")
if [ "${#sweep[@]}" -eq 0 ]; then
  sweep=(site/ templates/ data/ reports/)
fi

stripped=0
unrestored=0
while IFS= read -r -d '' f; do
  [ -f "$f" ] || continue
  grep -qI -e '^<<<<<<<' -- "$f" 2>/dev/null || continue
  grep -q -e '^>>>>>>>' -- "$f" 2>/dev/null || continue
  if git checkout HEAD -- "$f" 2>/dev/null; then
    stripped=$((stripped + 1))
    echo "stripped conflict wreckage: $f"
  else
    # not in HEAD (new file) — never stage it either
    git rm -q --cached --ignore-unmatch -- "$f" 2>/dev/null || true
    unrestored=$((unrestored + 1))
    echo "conflict wreckage in $f has no HEAD version — unstaged, left in tree"
  fi
done < <(git diff HEAD --name-only -z -- "${sweep[@]}" 2>/dev/null)

if [ "$stripped" -gt 0 ] || [ "$unrestored" -gt 0 ]; then
  echo "::warning title=conflict-marker wreckage stripped::${stripped} dirty file(s) carried git conflict markers (conflicted stash/rebase apply — 2026-08-01 d29e4dd44d class) and were restored from HEAD instead of committed; ${unrestored} had no HEAD version and were unstaged"
fi
exit 0
