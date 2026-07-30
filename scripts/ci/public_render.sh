#!/usr/bin/env bash
set -e
set -u
set -o pipefail

# Fast, data-free public-surface render. This intentionally does not invoke any
# market builder, restore a parquet cache, publish R2 data, or use a self-hosted
# runner. The PR already carries direct template/site pairs; this pass renders
# the three Jinja public pages and refreshes immutable asset stamps site-wide.
PUBLIC_OUTPUTS=(site/plans.html site/support.html site/unsubscribe.html)

render_public() {
  python -m scripts.build_public_pages
  python -m scripts.inject_data_base
  python -m scripts.externalize_css
  python -m scripts.optimize_assets
  python -m scripts.check_template_site_sync --fix
}

guard_public_outputs() {
  # Only these three pages are rendered from Jinja in this lane. The other
  # site-wide transforms add an external data-base tag, lift CSS, and update
  # src/href attributes; none edits executable inline JS. PR CI already proved
  # the rest of the committed site. Re-scanning all ~3,263 pages took ~2m30s
  # after EVERY lost main-ref race and made the retry itself slower than the
  # repository's merge cadence (run 30505255868 exhausted 240s after two races).
  python3 scripts/check_inline_js.py "${PUBLIC_OUTPUTS[@]}"
  python3 scripts/check_ms_board_coherence.py
}

render_public
guard_public_outputs

git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
git add site/ templates/

if git diff --cached --quiet; then
  echo "public surfaces already current; nothing to commit"
  exit 0
fi

git commit -m "render-public: public pages + asset stamps"

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
PUSH_BUDGET_SECS=600
PUSH_MAX_ATTEMPTS=12
push_retry_init "public render"

while push_attempt; do
  PRE_SYNC_HEAD=$(git rev-parse HEAD)
  git fetch origin main || true
  if git pull --rebase -X theirs origin main \
      || bash scripts/rebase_autoresolve_hashed_css.sh; then
    # The common first attempt has no new upstream commit: push immediately.
    # Before this guard the lane needlessly repeated the whole site sweep and
    # full-tree JS scan even when `git pull` changed nothing, opening a new
    # multi-minute ref-race window after it had already synchronized.
    if [ "$(git rev-parse HEAD)" != "$PRE_SYNC_HEAD" ]; then
      # Main really advanced. Re-apply the deterministic transforms to that
      # exact tree, then validate only the three pages this lane renders.
      # Existing pages were proven before the rebase and the transforms do not
      # alter inline JS; a full-tree replay here caused the observed starvation.
      render_public
      guard_public_outputs
      git add site/ templates/
      if ! git diff --cached --quiet; then
        git commit --amend --no-edit
      fi
    else
      echo "main unchanged since the validated render; pushing without a redundant sweep"
    fi
    if push_do origin HEAD:main; then
      echo "pushed public render on attempt $PUSH_ATTEMPT"
      push_won
      exit 0
    fi
  fi
  push_abort_rebase
  push_backoff
done

push_lost
echo "::error title=public render NOT pushed::$PUSH_ATTEMPT attempts failed ($PUSH_STOP)"
exit 1
