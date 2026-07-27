#!/usr/bin/env bash
set -u
set -o pipefail

# Fast, data-free public-surface render. This intentionally does not invoke any
# market builder, restore a parquet cache, publish R2 data, or use a self-hosted
# runner. The PR already carries direct template/site pairs; this pass renders
# the three Jinja public pages and refreshes immutable asset stamps site-wide.

render_public() {
  python -m scripts.build_public_pages
  python -m scripts.inject_data_base
  python -m scripts.externalize_css
  python -m scripts.optimize_assets
  python -m scripts.check_template_site_sync --fix
  python3 scripts/check_inline_js.py site
  python3 scripts/check_ms_board_coherence.py
}

render_public

git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
git add site/ templates/

if git diff --cached --quiet; then
  echo "public surfaces already current; nothing to commit"
  exit 0
fi

git commit -m "render-public: pricing, support, landing assets"

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
PUSH_BUDGET_SECS=240
PUSH_MAX_ATTEMPTS=12
push_retry_init "public render"

while push_attempt; do
  git fetch origin main || true
  if git pull --rebase -X theirs origin main \
      || bash scripts/rebase_autoresolve_hashed_css.sh; then
    # Main may have advanced while this short job ran. Re-render against that
    # exact tree, fold any delta into the existing bot commit, then push.
    render_public
    git add site/ templates/
    if ! git diff --cached --quiet; then
      git commit --amend --no-edit
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
