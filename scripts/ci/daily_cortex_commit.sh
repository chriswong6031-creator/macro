#!/usr/bin/env bash
# EXTRACTED-VERBATIM-FROM: .github/workflows/daily.yml
# job `cortex`, step `commit cortex outputs`.
# 2026-08-12 512KB processing-cap diet (tests/test_workflow_file_size.py).
# Env comes from the step's `env:` block, which stays in the YAML.
# Invoked as: bash scripts/ci/daily_cortex_commit.sh
set -e  # mirror GitHub's default `bash -e {0}` step shell — daily.yml declares no shell:

. "${GITHUB_WORKSPACE:-.}/scripts/ci/push_retry.sh"
git config user.name "dashboard-bot"
git config user.email "actions@users.noreply.github.com"
# Own commit lane (W7b PR2 + P1-D): all cortex + factor_attention subtrees — STAGING LAW
git add data/reflexes/cortex_attention/ 2>/dev/null || true
git add data/reflexes/factor_attention/grades.jsonl 2>/dev/null || true
git add data/reflexes/factor_attention/probation.json 2>/dev/null || true
git add data/neuralweb/cortex/ 2>/dev/null || true
git add data/neuralweb/machine_registry.jsonl 2>/dev/null || true
git add data/neuralweb/governance.jsonl 2>/dev/null || true
# trial_ledger: metabolism declares 1 budget row per accepted registration
# (log_declared_budget family='cortex'); unstaged it dies with this checkout
# and the DSR haircut undercounts.
git add data/trial_ledger.jsonl 2>/dev/null || true
git add site/neuralweb/ 2>/dev/null || true
# PR-C: NW health refresh (cortex_source=current_run) — two-phase health surface
git add data/neuralweb/health.json 2>/dev/null || true
git add site/neuralwebdata/health.json 2>/dev/null || true
# PR-D: NW daily brief finalize (phase=final + history row) — two-phase brief surface
git add data/neuralweb/daily_brief.json 2>/dev/null || true
git add site/neuralwebdata/daily_brief.json 2>/dev/null || true
git add data/neuralweb/daily_brief_history.jsonl 2>/dev/null || true
# W-AI: orchestrator run log + N-run reviews (recorded in THIS job — same commit lane)
git add data/neuralweb/orchestrator_runlog.jsonl 2>/dev/null || true
git add data/neuralweb/orchestrator_reviews.jsonl 2>/dev/null || true
git add site/neuralwebdata/orchestrator_runlog.json 2>/dev/null || true
# R-CI7: nw-context-intelligence W3 personality risk lens (display-only)
git add data/neuralweb/context_risk.json 2>/dev/null || true
git add site/neuralwebdata/context_risk.json 2>/dev/null || true
# W4 context scanner: narrow git-add of context_candidates.jsonl only (R-CI6)
git add data/neuralweb/context_candidates.jsonl 2>/dev/null || true
if git diff --cached --quiet; then echo "no cortex output changes"; exit 0; fi
git commit -m "cortex: attention grades + A2 earn-in + hypothesis metabolism $(date -u +%F)"
# Retry-rebase push loop (stock_briefs pattern)
PUSH_ALARM=420
push_retry_init "cortex outputs"
while push_attempt; do
  # pre-sync collision sweep (render.yml / #2252): a mid-run commit on origin/main can
  # TRACK a path this job wrote as an UNTRACKED side-effect — the rebase checkout then
  # refuses ("untracked working tree files would be overwritten") and --autostash can't
  # clear it (it parks tracked modifications only), so every retry dies identically.
  # Everything this step publishes is already committed above, so a path untracked HERE
  # but tracked on origin/main is a throwaway local write — origin/main is authoritative.
  # Gitignored files and untracked paths origin/main doesn't track never enter the
  # intersection (runner-local stores and caches are untouched).
  perl -e 'alarm 120; exec @ARGV or die' -- git fetch origin main || true
  comm -12 <(git ls-files --others --exclude-standard | LC_ALL=C sort) \
           <(git ls-tree -r --name-only origin/main | LC_ALL=C sort) \
    | while IFS= read -r f; do rm -f -- "$f" || true; done
  # F3 FIX: plain rebase (no -X theirs) so an adjacent-append conflict
  # on shared JSONL paths (trial_ledger, governance, machine_registry)
  # surfaces as a conflict → the retry re-runs cleanly instead of
  # silently dropping the causal job's committed rows.
  if perl -e 'alarm 420; exec @ARGV or die' -- git pull --rebase --autostash origin main && push_autostash_ok; then
    if push_do; then echo "pushed cortex outputs on attempt $PUSH_ATTEMPT"; push_won; exit 0; fi
  fi
  push_abort_rebase
  push_backoff
done
push_lost
echo "::warning::could not push cortex after $PUSH_ATTEMPT attempts ($PUSH_STOP) (non-fatal — downstream reads last committed)"
